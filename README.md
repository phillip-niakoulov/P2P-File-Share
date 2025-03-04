# P2P File Share
### Overview
This application allows peers to discover each other via the central registry server to be able to share and download files.

### Peer (`peer.py`)
Users interact with a text UI to find users, discover their files, and download files.

1. Receives a list of addresses from the registry and logs its own.
2. Sends all peers a list of their own files for them to store.
3. Receive file lists from peers and wait for file download requests.
    - If a download is requested, send 1 packet at a time, waiting for an ACK.
4. Depending on user input, list users or download files.
5. Periodically send files to peers to refresh file list and confirm which peers are still up.

### Registry (`registry.py`)
Runs in the background to store users connected to the P2P network.

1. Receives addresses from connecting peers.
2. Adds them to its repository.
3. Sends its repository to each peer.

### File Transfer Protocol
The P2P file transfer protocol uses custom messages to manage file sharing:

* **O (Offer)**: Sent by a peer to notify others about available files.
* **R (Request)**: Sent by a peer requesting a specific file.
* **T (Transfer)**: Sent by the source peer to send file chunks, each with a checksum for data integrity.
* **A (Acknowledgment)**: Sent by the receiving peer to confirm the receipt of each chunk.

File Transfer Flow:

1. **Offer**: A peer shares its file list with others.
2. **Request**: A peer requests a file from another peer.
3. **Transfer**: File chunks are sent, each verified with a checksum.
4. **Acknowledge**: The receiving peer acknowledges successful receipt of each chunk.

### Running
* `python registry.py`
* `python peer.py <port> <directory>`
    * `list`: Displays all available peers and their shared files.
    * `download <userId> <fileName>`: Downloads a file from the specified peer.
    * `exit`: Exits the peer program.
    * Avoid running with the directory root or any recursive file systems.