import socket
import json
import threading
import sys
import struct
import hashlib
import os
import time

def generate_uid(address):
    return hashlib.sha256(f"{address[0]}:{address[1]}".encode()).digest()

def checksum(data):
    return sum(data) % 65535

class Peer:
    def __init__(self, port, directory, host='127.0.0.1'):
        self.address = (host, port)
        self.threads = []
        self.server_thread = None
        self.peers = {} # uid_bytes: address = (ip, port), file-names = set(), "index" = int
        self.uid = generate_uid(self.address)[:4]
        self.directory = directory
        self.connections = 0

        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.bind(self.address)

        self.update_event = threading.Event()
        self.stop_event = threading.Event()
    

    def fetch_peer_info(self):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.connect(("localhost", 12345))

                sock.sendall(json.dumps({"host": self.address[0], "port": self.address[1]}).encode('utf-8'))

                data = sock.recv(1024)
                
                for peer in json.loads(data.decode('utf-8')):
                    peer_address = (peer['host'], peer['port'])
                    if peer_address != self.address:
                        peer_uid = generate_uid(peer_address)[:4]

                        if peer_uid not in self.peers:
                            self.peers[peer_uid] = [peer_address, set(), self.connections]
                            self.connections += 1
                        else:
                            self.peers[peer_uid][0] = peer_address

        except (socket.timeout, ConnectionRefusedError) as e:
            print("Error: Connection to registry failed. Please check the registry server.")
            return -1

    def get_all_files(self):
        file_paths = []
        
        for dirpath, dirnames, filenames in os.walk(self.directory):
            for filename in filenames:
                full_path = os.path.join(dirpath, filename)
                file_paths.append(full_path)

        return file_paths

    def start_server(self):
        self.socket.listen(10)
        # print(f"Server listening on {self.address[0]}:{self.address[1]}")

        while True:
            conn, addr = self.socket.accept()
            # print(f"Accepted connection from {addr}")
            threading.Thread(target=self.handle_incoming, args=(conn, addr)).start()

    def handle_incoming(self, conn, addr):
        new_uid = None
        try:
            while True:
                data = conn.recv(4096)
                
                if not data:
                    break

                msg_type, = struct.unpack("!B", data[:1])

                if msg_type == ord('O'):
                    _, uid, filename_bytes = struct.unpack("!B4s32s", data)
                    filename = filename_bytes.decode('utf-8').strip('\x00')

                    if uid not in self.peers:
                        self.peers[uid] = [None, set(), self.connections]
                        self.connections += 1
                        new_uid = uid

                    self.peers[uid][1].add(filename)

                    conn.sendall(struct.pack("!B4s", ord('A'), self.uid))
                
                elif msg_type == ord('R'):
                    _, filename_bytes = struct.unpack("!B32s", data)
                    filename = filename_bytes.decode('utf-8').strip('\x00')

                    with open(filename, 'rb') as file:
                        while True:
                            data = file.read(1024)
                            if not data: # EOF
                                break
                            
                            conn.sendall(struct.pack("!BH1024s", ord('T'), checksum(data), data))

                            ack = conn.recv(1024)
                            msg_type, = struct.unpack("!B", ack[:1])

                            if msg_type != ord('A'):
                                print("Error: Acknowledgment not received correctly")
                                break
                    # print("Sent whole file")

        except Exception as e:
            print(f"Error: Exception occurred while handling incoming data from {addr}: {e}")
        finally:
            conn.close()
        
        if new_uid:
            self.fetch_peer_info()
            thread = threading.Thread(target=self.send_file_list, args=(self.peers[new_uid][0],))
            thread.start()
            self.threads.append(thread)
        
    def download_file(self, address, file_name):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.connect(address)
                sock.settimeout(2)

                sock.sendall(struct.pack("!B32s", ord('R'), file_name.encode('utf-8')))
                with open(file_name.split('/')[-1], 'wb') as file:
                    while True:
                        try:
                            data = sock.recv(1027)
                            if not data:
                                break

                            msg_type, received_checksum, chunk = struct.unpack('!BH1024s', data)
                            if checksum(chunk) != received_checksum:
                                print(f"Error: Mismatched checksums while downloading {file_name}.")
                                file.close()
                                os.remove(file_name.split('/')[-1])
                                break

                            # print("chunk:", chunk.rstrip(b'\x00'))
                            file.write(chunk.rstrip(b'\x00'))
                            # print(f"Received chunk of size {len(chunk.rstrip(b'\x00'))} bytes")
                            sock.sendall(struct.pack("!B4s", ord('A'), self.uid))
                        except socket.timeout:
                            break
                print(f"Downloaded: {file_name}")
        except (socket.timeout, ConnectionRefusedError, TimeoutError) as e:
            print(f"Error: Could not download {file_name} from {address}. Peer might be unavailable.")
            del self.peers[generate_uid(address)[:4]]

    def send_file_list(self, peer_address):
        file_list = self.get_all_files()
        try:

            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.connect(peer_address)

                for file in file_list:
                    packet = struct.pack("!B4s32s", ord('O'), self.uid, file.encode('utf-8'))
                    sock.sendall(packet)
                    
                    ack = sock.recv(1024)
                    msg_type, = struct.unpack("!B", ack[:1])

                    if msg_type != ord('A'):
                        print(f"Error: Did not receive acknowledgment for file {file}.")
                        break
        except (socket.error, ConnectionRefusedError, TimeoutError) as e:
            del self.peers[generate_uid(peer_address)[:4]]

    def periodic_update(self):
        while not self.stop_event.is_set():
            time.sleep(15)
            # self.fetch_peer_info()
            for peer in self.peers:
                peer_address = self.peers[peer][0]
                threading.Thread(target=self.send_file_list, args=(peer_address,)).start()

    def start(self):
        if self.fetch_peer_info() == -1:
            print("Error: Couldn't connect to registry. Closing...")
            self.stop()

        print(f"Found {len(self.peers)} peer(s) in registry...")

        self.server_thread = threading.Thread(target=self.start_server, daemon=True)
        self.server_thread.start()
        
        for peer in self.peers:
            peer_address = self.peers[peer][0]
            thread = threading.Thread(target=self.send_file_list, args=(peer_address,))
            thread.start()
            self.threads.append(thread)

        periodic_thread = threading.Thread(target=self.periodic_update, daemon=True)
        periodic_thread.start()
        
        for thread in self.threads:
            thread.join()
        
        print('''Commands:
        "list": Prints user IDs and their files.
        "download <userId> <fileName>": Downloads a file from the specified user.
        "exit": Exits program.''')
        while True:
            user_input = input("> ").strip().lower()
            if user_input.startswith("list"):
                if len(self.peers) == 0: print("No peers found")
                for peer in self.peers:
                    print(f"{self.peers[peer][2]}: {list(self.peers[peer][1])}")
            elif user_input.startswith("download"):
                input_split = user_input.split()
                if len(input_split) == 3:
                    user_id = input_split[1]
                    file_name = input_split[2]
                    try:
                        found_peer = None

                        for peer in self.peers:
                            if self.peers[peer][2] == int(user_id):
                                found_peer = self.peers[peer]

                        if found_peer:
                            if file_name in found_peer[1]:
                                thread = threading.Thread(target=self.download_file, args=(found_peer[0], file_name))
                                thread.start()
                                thread.join()
                            else:
                                print(f"Error: User {user_id} doesn't have the file {file_name}.")
                        else:
                            print(f"Error: Unknown user: {user_id}.")
                        
                    except ValueError:
                        print(f"Error: Unknown user: {user_id}.")

                else:
                    print("Error: Invalid format, please use: download <userId> <fileName>")
            elif user_input.startswith("exit"):
                self.stop()
            else:
                print("Error: Unknown command.")

    def stop(self):
        self.socket.close()
        self.stop_event.set()
        sys.exit()



if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Error: Invalid format, please use: python peer.py <port> <directory>")
    else:
        try:
            peer = Peer(int(sys.argv[1]), sys.argv[2])
            try:
                peer.start()
            except KeyboardInterrupt:
                print("\nExiting...")
                peer.stop()
        except ValueError:
            print(f"Error: {sys.argv[1]} is not a valid port.")