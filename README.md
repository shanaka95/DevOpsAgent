# DevOpsAgent

An AI-powered DevOps automation agent built with LangGraph that can perform system administration tasks both locally and on remote servers through SSH.

## Features

- Execute shell commands on local or remote servers
- Manage SSH connections to remote servers
- Read and write files both locally and remotely
- Perform HTTP requests using curl
- Configure and deploy applications (like React) on fresh servers
- Execute complex, multi-step DevOps workflows autonomously

## Requirements

- Python 3.11+
- OpenAI or Anthropic API key (for the LLM)
- Tavily API key (for web search capabilities)

## Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/shanaka95/DevOpsAgent
   cd DevOpsAgent
   ```

2. Create a virtual environment and install dependencies:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install -e .
   ```

3. Create a `.env` file with your API keys:
   ```
   # Required for the agent's LLM
   ANTHROPIC_API_KEY=your_anthropic_api_key
   # OR
   OPENAI_API_KEY=your_openai_api_key
   
   # For web search capabilities
   TAVILY_API_KEY=your_tavily_api_key
   ```

## Usage

### Starting the Agent

You can run the DevOpsAgent using any of these methods:

#### LangGraph Studio
```bash
langgraph studio
```
Then open your browser at http://localhost:3000 and select the DevOpsAgent template.

#### LangGraph Dev Server
```bash
langgraph dev
```
This starts the development server with a web interface at http://localhost:3000 where you can interact with the agent.

### SSH Operations

The agent can connect to and operate on remote servers. Here are some example prompts:

```
Connect to my server at 192.168.1.100 with username admin and password Secure123!
```

```
Deploy a basic React application on the connected SSH server
```

```
Check the status of nginx on the connected server
```

### Local Operations

The agent can also run commands on your local system:

```
Create a new React project in the ~/projects directory
```

```
Check if Docker is running on this system
```

### File Operations

You can have the agent read, write, or edit files:

```
Read the /etc/hosts file on the remote server
```

```
Create a new nginx configuration file for my React app
```

### Web Operations

The agent can make HTTP requests:

```
Check if my website at https://example.com is responding
```

## Available Tools

The agent has access to the following tools:

1. `search` - Web search using Tavily
2. `run_shell_command` - Execute shell commands locally
3. `edit_file` - Read, write, or edit local files
4. `ssh_connect` - Connect to a remote server via SSH
5. `ssh_execute` - Run commands on a connected SSH server
6. `ssh_read_file` - Read files from a remote server
7. `ssh_write_file` - Write files to a remote server
8. `ssh_disconnect` - Close an SSH connection
9. `ssh_check_output` - Check output from a previous SSH command
10. `curl_check_url` - Make HTTP requests locally or remotely

## Security Considerations

- The agent will never use interactive commands like vim, nano, or less
- It follows best security practices for server configuration
- It will request clarification before executing potentially harmful commands
- SSH connections are managed securely with proper authentication

## Examples

### Configuring a React Application on a Fresh Server

```
I need to set up a React application on my new Ubuntu server. 
The server is at 192.168.1.100, username: admin, password: MySecurePass123.
Install Node.js, nginx, clone my React repo from https://github.com/myuser/myreactapp.git,
build it, and configure nginx to serve it.
```

### Troubleshooting a Web Server

```
My web server at 192.168.1.100 (username: admin, password: SecurePass123) 
isn't responding. Connect to it, check nginx status, inspect the logs,
and restart the service if needed.
```

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the LICENSE file for details.