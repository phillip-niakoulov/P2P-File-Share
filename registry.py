import socket
import threading
import json

class TCPServer:
    def __init__(self, host='0.0.0.0', port=12345):
        self.host = host
        self.port = port
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.received_data = []
        self.stop_event = threading.Event()

    def start(self):
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen(5)
        print(f"Server listening on {self.host}:{self.port}")

        while not self.stop_event.is_set():
            try:
                client_socket, addr = self.server_socket.accept()
                # print(f"Connection from {addr}")

                client_thread = threading.Thread(target=self.handle_client, args=(client_socket, addr))
                client_thread.daemon = True
                client_thread.start()
            except OSError:
                break

    def handle_client(self, client_socket, addr):
        try:
            data = client_socket.recv(1024)
            if data:
                try:
                    received_json = json.loads(data.decode('utf-8'))
                    print(f"Received data from {addr}: {received_json}")

                    self.received_data.append(received_json)

                    response = json.dumps(self.received_data)
                    client_socket.sendall(response.encode('utf-8'))

                except json.JSONDecodeError:
                    print(f"Invalid JSON received from {addr}")
                    response = json.dumps({"error": "Invalid JSON"})
                    client_socket.sendall(response.encode('utf-8'))

        except Exception as e:
            print(f"Error handling client {addr}: {e}")
        finally:
            client_socket.close()

    def stop(self):
        self.stop_event.set()
        self.server_socket.close()
        print("Server stopped.")

if __name__ == "__main__":
    server = TCPServer()
    try:
        server.start()
    except KeyboardInterrupt:
        server.stop()
