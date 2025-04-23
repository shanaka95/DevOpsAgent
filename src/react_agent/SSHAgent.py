import pexpect
import re
import os
import threading
import time

class SSHAgent:
    def __init__(self, hostname, port, username, password=None, pkey_path=None):
        # Build SSH command
        ssh_command = f"ssh {username}@{hostname} -p {port}"
        
        # Add identity file if provided
        if pkey_path:
            ssh_command += f" -i {pkey_path}"
        
        # Spawn the SSH process
        self.child = pexpect.spawn(ssh_command, encoding='utf-8')
        
        # Handle login
        if not pkey_path:
            self.child.expect(['password:', 'Password:'])
            self.child.sendline(password)
        
        # Wait for prompt
        self.child.expect(['[$#>]'])
        
        # Buffer for output
        self.output_buffer = ""
        self.lock = threading.Lock()
        
        # SCP options for file transfer
        self.hostname = hostname
        self.port = port
        self.username = username
        self.password = password
        self.pkey_path = pkey_path
        
        # Start background reader thread
        self.keep_reading = True
        self.reader_thread = threading.Thread(target=self._read_output)
        self.reader_thread.start()
    
    def _strip_ansi(self, text):
        ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
        return ansi_escape.sub('', text)
    
    def _read_output(self):
        while self.keep_reading:
            try:
                # Check if there's output to read (non-blocking)
                index = self.child.expect([pexpect.TIMEOUT, '.+'], timeout=0.1)
                if index == 1:  # Got some output
                    with self.lock:
                        self.output_buffer += self.child.match.group(0)
            except Exception as e:
                # Handle any exceptions
                pass
            time.sleep(0.1)
    
    def send_command(self, cmd):
        env_vars = 'PAGER=cat SYSTEMD_PAGER= DEBIAN_FRONTEND=noninteractive '
        self.child.sendline(cmd)
        # Wait a moment for command to start
        time.sleep(0.1)
    
    def get_output(self, strip_ansi=True):
        with self.lock:
            output = self.output_buffer
            self.output_buffer = ""  # Clear after reading
        return self._strip_ansi(output) if strip_ansi else output
    
    def read_file(self, remote_path):
        try:
            # Create a temporary file
            local_path = f"/tmp/sshagent_tmp_{os.getpid()}"
            
            # Build SCP command
            scp_command = f"scp -P {self.port}"
            if self.pkey_path:
                scp_command += f" -i {self.pkey_path}"
            
            scp_command += f" {self.username}@{self.hostname}:{remote_path} {local_path}"
            
            # Run SCP command
            if self.password:
                # Use pexpect for password authentication
                scp = pexpect.spawn(scp_command, encoding='utf-8')
                scp.expect(['password:', 'Password:'])
                scp.sendline(self.password)
                scp.expect(pexpect.EOF)
            else:
                # Use os.system for key-based authentication
                os.system(scp_command)
            
            # Read the file
            with open(local_path, 'r') as f:
                content = f.read()
            
            # Clean up
            os.remove(local_path)
            return content
        except Exception as e:
            return f"Error reading file: {e}"
    
    def write_file(self, remote_path, content):
        try:
            # Create a temporary file
            local_path = f"/tmp/sshagent_tmp_{os.getpid()}"
            
            # Write content to temporary file
            with open(local_path, 'w') as f:
                f.write(content)
            
            # Build SCP command
            scp_command = f"scp -P {self.port}"
            if self.pkey_path:
                scp_command += f" -i {self.pkey_path}"
            
            scp_command += f" {local_path} {self.username}@{self.hostname}:{remote_path}"
            
            # Run SCP command
            if self.password:
                # Use pexpect for password authentication
                scp = pexpect.spawn(scp_command, encoding='utf-8')
                scp.expect(['password:', 'Password:'])
                scp.sendline(self.password)
                scp.expect(pexpect.EOF)
            else:
                # Use os.system for key-based authentication
                os.system(scp_command)
            
            # Clean up
            os.remove(local_path)
            return "File updated successfully."
        except Exception as e:
            return f"Error writing file: {e}"
    
    def close(self):
        self.keep_reading = False
        self.reader_thread.join()
        self.child.sendline("exit")
        self.child.close()
