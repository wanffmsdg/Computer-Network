import socket
import struct
import random
import sys
import os

def main():
    # 解析命令行参数
    if len(sys.argv) != 6:
        print("Usage: python client.py <serverIP> <serverPort> <Lmin> <Lmax> <filename>")
        return
    
    serverIP = sys.argv[1]
    serverPort = int(sys.argv[2])
    Lmin = int(sys.argv[3])
    Lmax = int(sys.argv[4])
    filename = sys.argv[5]
    
    # 读取文件内容
    try:
        with open(filename, 'r') as f:
            content = f.read()
    except Exception as e:
        print(f"Error reading file: {e}")
        return
    
    # 计算块数和分块
    blocks = []
    total_len = len(content)
    start = 0
    
    while start < total_len:
        # 最后一块特殊处理
        if total_len - start <= Lmax:
            block_len = total_len - start
        else:
            block_len = random.randint(Lmin, Lmax)
        
        block = content[start:start+block_len]
        blocks.append(block)
        start += block_len
    
    N = len(blocks)  # 总块数
    
    # 连接服务器
    try:
        client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)#AF_IENT表示使用IPv4地址, SOCK_STREAM表示使用TCP协议
        client_socket.connect((serverIP, serverPort))
        
        # 发送Initialization报文 (Type=1, N)
        init_packet = struct.pack('>HI', 1, N)
        client_socket.sendall(init_packet)
        
        # 接收Agree报文 (Type=2)
        agree_packet = client_socket.recv(2)#参数为最多接收的字节数
        if len(agree_packet) < 2 or struct.unpack('>H', agree_packet)[0] != 2:
            print("Protocol error: Expected agree packet")
            return
        
        # 发送和接收所有块
        reversed_content = ""
        for i, block in enumerate(blocks):
            # 发送reverseRequest报文 (Type=3, Length, Data)
            data = block.encode('utf-8')
            request_header = struct.pack('>HI', 3, len(data))
            client_socket.sendall(request_header + data)
            
            # 接收reverseAnswer报文 (Type=4, Length, reverseData)
            answer_header = client_socket.recv(6)
            if len(answer_header) < 6:
                print("Protocol error: Incomplete answer header")
                break
                
            type_val, length = struct.unpack('>HI', answer_header)#第一个元素是根据H格式解析得到的无符号短整型值，第二个元素是根据I格式解析得到的无符号整型值。
            if type_val != 4:
                print(f"Protocol error: Expected answer packet, got type {type_val}")
                break
                
            reversed_data = b''
            while len(reversed_data) < length:
                chunk = client_socket.recv(length - len(reversed_data))
                if not chunk:
                    break
                reversed_data += chunk
                
            if len(reversed_data) != length:
                print(f"Incomplete data received: expected {length}, got {len(reversed_data)}")
                break
                
            # 处理反转数据
            reversed_text = reversed_data.decode('utf-8')
            reversed_content += reversed_text
            print(f"第 {i+1} 块: {reversed_text}")
        
        # 保存最终反转文件
        output_filename = os.path.splitext(filename)[0] + "_reversed.txt"
        with open(output_filename, 'w') as f:
            f.write(reversed_content)
        print(f"Final reversed file saved as: {output_filename}")
            
    except Exception as e:
        print(f"Error: {e}")
    finally:
        client_socket.close()

if __name__ == "__main__":
    main()