"""This module provides example tools for web scraping and search functionality.

It includes a basic Tavily search function (as an example)

These tools are intended as free examples to get started. For production use,
consider implementing more robust and specialized tools tailored to your needs.
"""

from typing import Any, Callable, Dict, List, Optional, cast
import subprocess
import shlex
import asyncio
import os
import pathlib
from asyncio.subprocess import Process

from langchain_community.tools.tavily_search import TavilySearchResults
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import InjectedToolArg
from typing_extensions import Annotated

from react_agent.configuration import Configuration
from react_agent.SSHAgent import SSHAgent

# Create a file operation lock to prevent concurrent file operations
_file_lock = asyncio.Lock()

# Global SSH connection storage
_ssh_connections: Dict[str, SSHAgent] = {}


async def search(
    query: str, *, config: Annotated[RunnableConfig, InjectedToolArg]
) -> Optional[list[dict[str, Any]]]:
    """Search for general web results.

    This function performs a search using the Tavily search engine, which is designed
    to provide comprehensive, accurate, and trusted results. It's particularly useful
    for answering questions about current events.
    """
    configuration = Configuration.from_runnable_config(config)
    wrapped = TavilySearchResults(max_results=configuration.max_search_results)
    result = await wrapped.ainvoke({"query": query})
    return cast(list[dict[str, Any]], result)


async def run_shell_command(
    command: str, 
    *,
    responses: List[dict] = None,
    timeout: int = 30,
    config: Annotated[RunnableConfig, InjectedToolArg]
) -> str:
    """Execute a Linux shell command and return the output.
    
    This function executes a Linux shell command on local machine and returns the output.
    It can handle interactive commands that prompt for user input.
    
    Args:
        command: The shell command to execute
        responses: List of dict with 'prompt' and 'response' keys for interactive commands
        timeout: Maximum execution time in seconds
    """
    try:
        # Parse the command properly
        args = shlex.split(command)
        
        if not responses:
            # Non-interactive mode - simpler execution
            # Create subprocess asynchronously
            process = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            # Set a timeout for the command execution
            try:
                stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
                
                # Decode bytes to string
                output = stdout.decode('utf-8')
                error_output = stderr.decode('utf-8')
                
                # Combine stdout and stderr if needed
                if error_output:
                    output += f"\nError output:\n{error_output}"
                    
                return output
            except asyncio.TimeoutError:
                # Make sure to terminate the process if it times out
                process.kill()
                return f"Command timed out after {timeout} seconds"
        else:
            # Interactive mode - handle prompts and responses
            # Create subprocess with pipes for stdin, stdout, stderr
            process = await asyncio.create_subprocess_exec(
                *args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            # Track all output
            all_output = []
            remaining_responses = responses.copy()
            process_output = ""
            
            # Set up timeout
            end_time = asyncio.get_event_loop().time() + timeout
            
            # Run the interactive session
            while process.returncode is None:
                # Check if we've exceeded the timeout
                if asyncio.get_event_loop().time() > end_time:
                    process.kill()
                    return f"Interactive command timed out after {timeout} seconds"
                
                # Use a short timeout for reading to check for prompts
                try:
                    # Read a chunk from stdout without blocking too long
                    chunk = await asyncio.wait_for(
                        process.stdout.read(1024),
                        timeout=0.5
                    )
                    
                    if not chunk:  # EOF reached
                        break
                    
                    # Decode and store the output
                    chunk_str = chunk.decode('utf-8')
                    process_output += chunk_str
                    all_output.append(chunk_str)
                    
                    # Check if we need to respond to any prompts
                    for response_item in remaining_responses[:]:
                        prompt = response_item['prompt']
                        response = response_item['response']
                        
                        if prompt in process_output:
                            # Found a prompt that needs a response
                            if process.stdin.is_closing():
                                return "Error: Process stdin closed unexpectedly"
                                
                            # Send the response
                            process.stdin.write(f"{response}\n".encode('utf-8'))
                            await process.stdin.drain()
                            
                            # Add the response to the output log
                            all_output.append(f"[Sent: {response}]\n")
                            
                            # Remove this response from the list to avoid sending again
                            remaining_responses.remove(response_item)
                            
                            # Reset the output buffer after sending a response
                            process_output = ""
                            
                except asyncio.TimeoutError:
                    # No output for a while, just continue the loop
                    continue
                
                # Check if the process has ended
                if process.returncode is not None:
                    break
            
            # Collect any final output and close stdin
            if process.stdin and not process.stdin.is_closing():
                process.stdin.close()
            
            # Wait for the process to complete
            try:
                final_stdout, final_stderr = await asyncio.wait_for(
                    process.communicate(), 
                    timeout=max(1, end_time - asyncio.get_event_loop().time())
                )
                
                # Add any final output
                if final_stdout:
                    all_output.append(final_stdout.decode('utf-8'))
                if final_stderr:
                    all_output.append(f"Error output:\n{final_stderr.decode('utf-8')}")
            except asyncio.TimeoutError:
                process.kill()
                all_output.append(f"Process killed after timeout ({timeout}s)")
            
            # Return the combined output
            return "".join(all_output)
            
    except Exception as e:
        return f"Error executing command: {str(e)}"


async def edit_file(
    file_path: str, 
    content: str = "",
    mode: str = "write",
    read_type: str = "full",
    num_chars: int = 1000,
    *, 
    config: Annotated[RunnableConfig, InjectedToolArg]
) -> str:
    """Edit or read a file on the local filesystem.
    
    Args:
        file_path: Path to the file to edit or read
        content: Content to write to the file (ignored if mode is 'read')
        mode: Operation mode - 'write', 'append', or 'read'
        read_type: For read mode - 'full', 'head', or 'tail'
        num_chars: Number of characters to read for head/tail operations
    """
    try:
        # Ensure we're not trying to access files outside current directory
        path = pathlib.Path(file_path)
        if path.is_absolute():
            # Get current working directory using asyncio.to_thread to avoid blocking
            cwd = await asyncio.to_thread(pathlib.Path.cwd)
            # Make it relative to a safe base directory
            path = cwd / pathlib.Path(file_path).relative_to(pathlib.Path(file_path).anchor)
        
        # Create parent directories if they don't exist
        if mode in ["write", "append"]:
            # Move the blocking makedirs call to a separate thread
            await asyncio.to_thread(
                lambda p: os.makedirs(os.path.dirname(p) if os.path.dirname(p) else ".", exist_ok=True),
                path
            )
            
        if mode == "read":
            # Reading a file
            # Check file existence in a non-blocking way
            exists = await asyncio.to_thread(lambda p: p.exists(), path)
            if not exists:
                return f"Error: File {file_path} does not exist"
                
            # Use async file IO to avoid blocking
            async with _file_lock:
                # Use asyncio.to_thread for file operations to avoid blocking
                if read_type == "full":
                    # Read the entire file
                    file_content = await asyncio.to_thread(lambda p: p.read_text(), path)
                    return file_content
                elif read_type == "head":
                    # Read only the beginning of the file
                    def read_head(p, n):
                        with open(p, 'r') as f:
                            return f.read(n)
                    head_content = await asyncio.to_thread(read_head, path, num_chars)
                    return f"First {num_chars} characters of {file_path}:\n{head_content}"
                elif read_type == "tail":
                    # Read only the end of the file
                    def read_tail(p, n):
                        with open(p, 'r') as f:
                            # Get file size
                            f.seek(0, os.SEEK_END)
                            size = f.tell()
                            # Seek to the appropriate position
                            f.seek(max(0, size - n), os.SEEK_SET)
                            return f.read(n)
                    tail_content = await asyncio.to_thread(read_tail, path, num_chars)
                    return f"Last {num_chars} characters of {file_path}:\n{tail_content}"
                else:
                    return f"Error: Invalid read_type '{read_type}'. Use 'full', 'head', or 'tail'"
                
        elif mode == "write":
            # Writing to a file (overwrites existing content)
            async with _file_lock:
                await asyncio.to_thread(lambda p, c: p.write_text(c), path, content)
                return f"Successfully wrote {len(content)} characters to {file_path}"
                
        elif mode == "append":
            # Appending to a file
            exists = await asyncio.to_thread(lambda p: p.exists(), path)
            if exists:
                async with _file_lock:
                    # Read existing content
                    existing_content = await asyncio.to_thread(lambda p: p.read_text(), path)
                    # Append new content
                    await asyncio.to_thread(lambda p, c: p.write_text(c), path, existing_content + content)
                    return f"Successfully appended {len(content)} characters to {file_path}"
            else:
                # If file doesn't exist, create it with the content
                async with _file_lock:
                    await asyncio.to_thread(lambda p, c: p.write_text(c), path, content)
                    return f"File {file_path} did not exist. Created it with {len(content)} characters"
        else:
            return f"Error: Invalid mode '{mode}'. Use 'read', 'write', or 'append'"
            
    except Exception as e:
        return f"Error editing file: {str(e)}"


async def ssh_connect(
    hostname: str,
    port: int = 22,
    username: str = "",
    password: str = "",
    key_path: str = "",
    connection_id: str = "default",
    *,
    config: Annotated[RunnableConfig, InjectedToolArg]
) -> str:
    """Establish an SSH connection to a remote server.
    
    This tool creates a new SSH connection that can be used in subsequent calls.
    The connection will remain active throughout the session.
    
    Args:
        hostname: The hostname or IP address of the remote server
        port: The SSH port (default: 22)
        username: Username for authentication
        password: Password for authentication (leave empty if using key authentication)
        key_path: Path to private key file (leave empty if using password authentication)
        connection_id: Identifier for this connection to reference in future calls
    """
    global _ssh_connections
    
    try:
        # Check if we already have a connection with this ID
        if connection_id in _ssh_connections:
            # Close the existing connection first
            await asyncio.to_thread(lambda: _ssh_connections[connection_id].close())
            del _ssh_connections[connection_id]
        
        # Create the SSH connection in a non-blocking way
        ssh_agent = await asyncio.to_thread(
            lambda: SSHAgent(
                hostname=hostname,
                port=port,
                username=username,
                password=password if password else None,
                pkey_path=key_path if key_path else None
            )
        )
        
        # Store the connection for later use
        _ssh_connections[connection_id] = ssh_agent
        
        return f"SSH connection established to {hostname}:{port} as {username} (ID: {connection_id})"
    except Exception as e:
        return f"Error establishing SSH connection: {str(e)}"


async def ssh_execute(
    command: str,
    connection_id: str = "default",
    wait_time: float = 2.0,
    *,
    config: Annotated[RunnableConfig, InjectedToolArg]
) -> str:
    """Execute a command on a remote server via SSH.
    
    Runs the specified command on a previously established SSH connection. DO NOT USE THIS TOOL FOR FILE READING OR WRITING.
    
    Args:
        command: The shell command to execute on the remote server
        connection_id: The identifier of the SSH connection to use
        wait_time: Time to wait in seconds for command completion
    """
    global _ssh_connections
    
    try:
        # Check if the connection exists
        if connection_id not in _ssh_connections:
            return f"Error: No SSH connection found with ID '{connection_id}'. Use ssh_connect first."
        
        ssh = _ssh_connections[connection_id]
        
        # Send the command in a non-blocking way
        await asyncio.to_thread(lambda: ssh.send_command(command))
        
        # Wait for the command to execute
        await asyncio.sleep(wait_time)
        
        # Get the output in a non-blocking way
        output = await asyncio.to_thread(lambda: ssh.get_output())
        
        return output
    except Exception as e:
        return f"Error executing SSH command: {str(e)}"


async def ssh_read_file(
    remote_path: str,
    connection_id: str = "default",
    read_type: str = "full",
    num_chars: int = 1000,
    *,
    config: Annotated[RunnableConfig, InjectedToolArg]
) -> str:
    """Read a file from a remote server via SSH.
    
    Fetches the content of a file from a previously established SSH connection.
    
    Args:
        remote_path: The path to the file on the remote server
        connection_id: The identifier of the SSH connection to use
        read_type: How to read the file - 'full', 'head', or 'tail'
        num_chars: Number of characters to read for head/tail operations
    """
    global _ssh_connections
    
    try:
        # Check if the connection exists
        if connection_id not in _ssh_connections:
            return f"Error: No SSH connection found with ID '{connection_id}'. Use ssh_connect first."
        
        ssh = _ssh_connections[connection_id]
        
        if read_type == "full":
            # Read the entire file using the agent's method
            content = await asyncio.to_thread(lambda: ssh.read_file(remote_path))
            return content
        elif read_type == "head":
            # Use head command to get first part of file
            head_cmd = f"head -c {num_chars} {remote_path}"
            await asyncio.to_thread(lambda: ssh.send_command(head_cmd))
            await asyncio.sleep(1)  # Wait for command to complete
            content = await asyncio.to_thread(lambda: ssh.get_output())
            return f"First {num_chars} characters of {remote_path}:\n{content}"
        elif read_type == "tail":
            # Use tail command to get last part of file
            # First get file size to determine tail strategy
            size_cmd = f"wc -c < {remote_path}"
            await asyncio.to_thread(lambda: ssh.send_command(size_cmd))
            await asyncio.sleep(1)
            size_output = await asyncio.to_thread(lambda: ssh.get_output())
            
            try:
                # Parse file size
                size = int(size_output.strip())
                
                # Use tail command with appropriate option
                if size > num_chars:
                    tail_cmd = f"tail -c {num_chars} {remote_path}"
                else:
                    # If file is smaller than requested chars, just cat the whole file
                    tail_cmd = f"cat {remote_path}"
                    
                await asyncio.to_thread(lambda: ssh.send_command(tail_cmd))
                await asyncio.sleep(1)
                content = await asyncio.to_thread(lambda: ssh.get_output())
                return f"Last {min(num_chars, size)} characters of {remote_path}:\n{content}"
            except ValueError:
                # If size parsing fails, use a direct tail command
                tail_cmd = f"tail -c {num_chars} {remote_path}"
                await asyncio.to_thread(lambda: ssh.send_command(tail_cmd))
                await asyncio.sleep(1)
                content = await asyncio.to_thread(lambda: ssh.get_output())
                return f"Last {num_chars} characters of {remote_path}:\n{content}"
        else:
            return f"Error: Invalid read_type '{read_type}'. Use 'full', 'head', or 'tail'"
    except Exception as e:
        return f"Error reading remote file: {str(e)}"


async def ssh_write_file(
    remote_path: str,
    content: str,
    connection_id: str = "default",
    *,
    config: Annotated[RunnableConfig, InjectedToolArg]
) -> str:
    """Write a file to a remote server via SSH.
    
    Updates or creates a file on a previously established SSH connection.
    
    Args:
        remote_path: The path to the file on the remote server
        content: The content to write to the file
        connection_id: The identifier of the SSH connection to use
    """
    global _ssh_connections
    
    try:
        # Check if the connection exists
        if connection_id not in _ssh_connections:
            return f"Error: No SSH connection found with ID '{connection_id}'. Use ssh_connect first."
        
        ssh = _ssh_connections[connection_id]
        
        # Write the file in a non-blocking way
        result = await asyncio.to_thread(lambda: ssh.write_file(remote_path, content))
        
        return result
    except Exception as e:
        return f"Error writing remote file: {str(e)}"


async def ssh_disconnect(
    connection_id: str = "default",
    *,
    config: Annotated[RunnableConfig, InjectedToolArg]
) -> str:
    """Close an SSH connection to a remote server.
    
    Disconnects and removes a previously established SSH connection.
    
    Args:
        connection_id: The identifier of the SSH connection to close
    """
    global _ssh_connections
    
    try:
        # Check if the connection exists
        if connection_id not in _ssh_connections:
            return f"No SSH connection found with ID '{connection_id}'"
        
        # Close the connection in a non-blocking way
        await asyncio.to_thread(lambda: _ssh_connections[connection_id].close())
        
        # Remove from the dictionary
        del _ssh_connections[connection_id]
        
        return f"SSH connection closed (ID: {connection_id})"
    except Exception as e:
        return f"Error closing SSH connection: {str(e)}"


async def ssh_check_output(
    connection_id: str = "default",
    clear_buffer: bool = False,
    *,
    config: Annotated[RunnableConfig, InjectedToolArg]
) -> str:
    """Check the current output from an SSH connection.
    
    This tool retrieves any available output from the SSH connection without sending a new command.
    Useful for checking the progress of long-running commands.
    
    Args:
        connection_id: The identifier of the SSH connection to use
        clear_buffer: Whether to clear the output buffer after reading (default: False)
    """
    global _ssh_connections
    
    try:
        # Check if the connection exists
        if connection_id not in _ssh_connections:
            return f"Error: No SSH connection found with ID '{connection_id}'. Use ssh_connect first."
        
        ssh = _ssh_connections[connection_id]
        
        # Get the output in a non-blocking way
        output = await asyncio.to_thread(lambda: ssh.get_output())
        
        return output if output else "No new output available."
    except Exception as e:
        return f"Error checking SSH output: {str(e)}"


async def curl_check_url(
    url: str,
    method: str = "GET",
    headers: List[str] = None,
    data: str = None,
    output_type: str = "full",
    timeout: int = 30,
    follow_redirects: bool = True,
    connection_id: str = None,
    *,
    config: Annotated[RunnableConfig, InjectedToolArg]
) -> str:
    """Check a remote URL using curl.
    
    This tool makes HTTP requests to remote URLs using curl. If an SSH connection_id is provided,
    it runs the curl command on the remote server, otherwise it runs locally.
    
    Args:
        url: The URL to request
        method: HTTP method to use (GET, POST, PUT, DELETE, etc.)
        headers: List of headers to include (format: ["Key: Value", "Key2: Value2"])
        data: Data to send with the request (for POST, PUT, etc.)
        output_type: Response output format - 'full', 'headers', 'body', or 'status'
        timeout: Maximum time to wait for response in seconds
        follow_redirects: Whether to follow HTTP redirects
        connection_id: Optional SSH connection ID to run curl on remote server
    """
    try:
        # Build the curl command
        curl_cmd = ["curl", "-s"]
        
        # Add method if not GET
        if method != "GET":
            curl_cmd.extend(["-X", method])
            
        # Add headers
        if headers:
            for header in headers:
                curl_cmd.extend(["-H", header])
                
        # Add data if provided
        if data:
            curl_cmd.extend(["-d", data])
            
        # Add timeout
        curl_cmd.extend(["--max-time", str(timeout)])
        
        # Add follow redirects option
        if follow_redirects:
            curl_cmd.append("-L")
            
        # Add output options
        if output_type == "headers":
            curl_cmd.append("-I")  # Only fetch headers
        elif output_type == "status":
            curl_cmd.extend(["-o", "/dev/null", "-w", "%{http_code}"])  # Only return status code
        
        # Add the URL
        curl_cmd.append(url)
        
        # Convert to string command
        cmd_str = " ".join([shlex.quote(str(arg)) for arg in curl_cmd])
        
        # Execute the command (locally or via SSH)
        if connection_id:
            # Check if the connection exists
            if connection_id not in _ssh_connections:
                return f"Error: No SSH connection found with ID '{connection_id}'. Use ssh_connect first."
            
            ssh = _ssh_connections[connection_id]
            
            # Send the command
            await asyncio.to_thread(lambda: ssh.send_command(cmd_str))
            
            # Wait for completion with a bit of buffer time
            wait_time = min(timeout + 2, 120)  # Cap at 2 minutes
            await asyncio.sleep(wait_time * 0.2)  # Start with partial wait
            
            # Get initial output
            output = await asyncio.to_thread(lambda: ssh.get_output())
            
            # If output seems incomplete, wait more
            if not output or output.strip().endswith("..."):
                await asyncio.sleep(wait_time * 0.8)
                more_output = await asyncio.to_thread(lambda: ssh.get_output())
                output += more_output
            
            return output
        else:
            # Execute locally
            # Create subprocess asynchronously
            process = await asyncio.create_subprocess_exec(
                *curl_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            # Set a timeout for the command execution
            try:
                stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout + 5)
                
                # Decode bytes to string
                output = stdout.decode('utf-8')
                error_output = stderr.decode('utf-8')
                
                # Check for errors
                if process.returncode != 0:
                    if error_output:
                        return f"Curl error: {error_output}"
                    return f"Curl command failed with exit code {process.returncode}"
                
                # Return the appropriate output
                if error_output and not output:
                    return error_output
                return output
                
            except asyncio.TimeoutError:
                # Make sure to terminate the process if it times out
                process.kill()
                return f"Request timed out after {timeout} seconds"
    
    except Exception as e:
        return f"Error executing curl request: {str(e)}"


TOOLS: List[Callable[..., Any]] = [
    search, 
    run_shell_command, 
    edit_file,
    ssh_connect,
    ssh_execute,
    ssh_read_file,
    ssh_write_file,
    ssh_disconnect,
    ssh_check_output,
    curl_check_url
]
