import paramiko
import threading
import time
import re

class SSHAgent:
    def __init__(self, hostname, port, username, password=None, pkey_path=None):
        self.client = paramiko.SSHClient()
        self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        if pkey_path:
            pkey = paramiko.RSAKey.from_private_key_file(pkey_path)
            self.client.connect(hostname, port=port, username=username, pkey=pkey)
        else:
            self.client.connect(hostname, port=port, username=username, password=password)

        self.shell = self.client.invoke_shell(term='xterm')
        self.output_buffer = ""
        self.lock = threading.Lock()

        # SFTP session
        self.sftp = self.client.open_sftp()

        # Start background reader thread
        self.keep_reading = True
        self.reader_thread = threading.Thread(target=self._read_output)
        self.reader_thread.start()

    def _strip_ansi(self, text):
        ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
        return ansi_escape.sub('', text)

    def _read_output(self):
        while self.keep_reading:
            if self.shell.recv_ready():
                output = self.shell.recv(4096).decode('utf-8', errors='ignore')
                with self.lock:
                    self.output_buffer += output

                # Auto-handle common interactive prompts
                if "return" in output.lower() or "enter" in output.lower():
                    self.shell.send('\n')

            time.sleep(0.1)

    def send_command(self, cmd):
        self.shell.send('PAGER=cat SYSTEMD_PAGER= DEBIAN_FRONTEND=noninteractive ' + cmd + '\n')

    def get_output(self, strip_ansi=True):
        with self.lock:
            output = self.output_buffer
            self.output_buffer = ""  # Clear after reading
        return self._strip_ansi(output) if strip_ansi else output

    def read_file(self, remote_path):
        try:
            with self.sftp.open(remote_path, 'r') as f:
                return f.read().decode('utf-8')
        except Exception as e:
            return f"Error reading file: {e}"

    def write_file(self, remote_path, content):
        try:
            with self.sftp.open(remote_path, 'w') as f:
                f.write(content)
            return "File updated successfully."
        except Exception as e:
            return f"Error writing file: {e}"

    def close(self):
        self.keep_reading = False
        self.reader_thread.join()
        self.shell.close()
        self.sftp.close()
        self.client.close()
