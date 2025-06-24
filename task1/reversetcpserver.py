import socket
import struct
import threading

def handle_client(conn, addr):
    print(f"New connection from: {addr}")
    
    try:
        # 接收Initialization报文
        init_packet = conn.recv(6)
        if len(init_packet) < 6:
            print("Incomplete initialization packet")
            return
            
        type_val, N = struct.unpack('>HI', init_packet)
        if type_val != 1:
            print(f"Protocol error: Expected init packet, got type {type_val}")
            return
            
        print(f"Client requested to reverse {N} blocks")
        
        # 发送Agree报文
        agree_packet = struct.pack('>H', 2)
        conn.sendall(agree_packet)
        
        # 处理所有块
        for i in range(N):
            # 接收reverseRequest报文
            request_header = conn.recv(6)
            if len(request_header) < 6:
                print("Incomplete request header")
                break
                
            type_val, length = struct.unpack('>HI', request_header)
            if type_val != 3:
                print(f"Protocol error: Expected request packet, got type {type_val}")
                break
                
            # 接收数据
            data = b''
            while len(data) < length:#使用循环是因为确保在处理数据之前已经完整地接收到了所有内容，避免因数据不完整导致的处理错误
                chunk = conn.recv(length - len(data))
                if not chunk:
                    break
                data += chunk
                
            if len(data) != length:
                print(f"Incomplete data: expected {length}, got {len(data)}")
                break
                
            # 反转数据
            text = data.decode('utf-8')
            reversed_text = text[::-1]
            reversed_data = reversed_text.encode('utf-8')
            
            # 发送reverseAnswer报文
            answer_header = struct.pack('>HI', 4, len(reversed_data))
            conn.sendall(answer_header + reversed_data)
            
        print(f"Finished processing {addr}")
        
    except Exception as e:
        print(f"Error with {addr}: {e}")
    finally:
        conn.close()

def main():
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)#允许地址重用
    
    try:
        server_socket.bind(("172.27.169.160", 8888))
        server_socket.listen(5)
        print("Server started, waiting for connections...")
        
        while True:
            conn, addr = server_socket.accept()
            client_thread = threading.Thread(
                target=handle_client, # 指定线程要执行的目标函数
                args=(conn, addr)
            )
            client_thread.daemon = True# 将线程设置为守护线程（daemon thread）
            client_thread.start()
            
    except Exception as e:
        print(f"Server error: {e}")
    finally:
        server_socket.close()

if __name__ == "__main__":
    main()