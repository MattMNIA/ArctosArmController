#!/usr/bin/env python3
"""
Simple browser-based WebSocket test.
Open this file in a browser to test WebSocket connectivity.
"""

import http.server
import socketserver
import os

HTML_CONTENT = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>WebSocket Connection Test</title>
    <script src="https://cdn.socket.io/4.5.4/socket.io.min.js"></script>
    <style>
        body {
            font-family: monospace;
            max-width: 800px;
            margin: 50px auto;
            padding: 20px;
            background: #1e1e1e;
            color: #00ff00;
        }
        .log {
            background: #0d0d0d;
            padding: 10px;
            margin: 10px 0;
            border-left: 3px solid #00ff00;
            max-height: 400px;
            overflow-y: auto;
        }
        .error {
            color: #ff0000;
            border-left-color: #ff0000;
        }
        .success {
            color: #00ff00;
            border-left-color: #00ff00;
        }
        .warning {
            color: #ffff00;
            border-left-color: #ffff00;
        }
        h1 {
            color: #00ff00;
        }
        button {
            padding: 10px 20px;
            font-size: 16px;
            background: #00ff00;
            color: #000;
            border: none;
            cursor: pointer;
            margin: 10px 5px 10px 0;
        }
        button:hover {
            background: #00dd00;
        }
        .status {
            font-size: 18px;
            font-weight: bold;
            padding: 10px;
            margin: 10px 0;
            border-radius: 5px;
        }
        .connected {
            background: #00ff00;
            color: #000;
        }
        .disconnected {
            background: #ff0000;
            color: #fff;
        }
    </style>
</head>
<body>
    <h1>🤖 Robot WebSocket Diagnostic</h1>
    
    <div id="status" class="status disconnected">Status: Disconnected</div>
    
    <div>
        <button onclick="connect()">Connect</button>
        <button onclick="disconnect()">Disconnect</button>
        <button onclick="clearLog()">Clear Log</button>
    </div>
    
    <h2>Connection Log:</h2>
    <div id="log" class="log"></div>
    
    <h2>Received Events:</h2>
    <div id="events" class="log"></div>
    
    <script>
        let socket = null;
        let receivedEvents = {};
        
        function log(message, type = 'info') {
            const logDiv = document.getElementById('log');
            const timestamp = new Date().toLocaleTimeString();
            const entry = document.createElement('div');
            entry.className = type;
            entry.textContent = `[${timestamp}] ${message}`;
            logDiv.appendChild(entry);
            logDiv.scrollTop = logDiv.scrollHeight;
            console.log(message);
        }
        
        function updateStatus(connected) {
            const statusDiv = document.getElementById('status');
            if (connected) {
                statusDiv.textContent = 'Status: Connected ✓';
                statusDiv.className = 'status connected';
            } else {
                statusDiv.textContent = 'Status: Disconnected ✗';
                statusDiv.className = 'status disconnected';
            }
        }
        
        function connect() {
            if (socket && socket.connected) {
                log('Already connected', 'warning');
                return;
            }
            
            log('Attempting to connect to http://localhost:5000...', 'info');
            
            socket = io('http://localhost:5000', {
                transports: ['websocket', 'polling'],
                reconnection: true,
                reconnectionDelay: 1000,
                reconnectionDelayMax: 5000,
                reconnectionAttempts: 5
            });
            
            socket.on('connect', () => {
                log('✓ Connected to server', 'success');
                updateStatus(true);
            });
            
            socket.on('disconnect', (reason) => {
                log(`✗ Disconnected: ${reason}`, 'error');
                updateStatus(false);
            });
            
            socket.on('connect_error', (error) => {
                log(`✗ Connection error: ${error}`, 'error');
            });
            
            socket.on('status', (data) => {
                log(`📨 Received status: ${JSON.stringify(data)}`, 'success');
                recordEvent('status', data);
            });
            
            socket.on('telemetry', (data) => {
                log(`📊 Received telemetry: ${JSON.stringify(data)}`, 'success');
                recordEvent('telemetry', data);
            });
            
            // Log all other events
            socket.onAny((eventName, ...args) => {
                if (!['connect', 'disconnect', 'connect_error', 'status', 'telemetry'].includes(eventName)) {
                    log(`📨 Event '${eventName}': ${JSON.stringify(args)}`, 'warning');
                }
            });
        }
        
        function disconnect() {
            if (socket) {
                socket.disconnect();
                log('Disconnected', 'warning');
                updateStatus(false);
            }
        }
        
        function clearLog() {
            document.getElementById('log').innerHTML = '';
            document.getElementById('events').innerHTML = '';
        }
        
        function recordEvent(name, data) {
            receivedEvents[name] = data;
            const eventsDiv = document.getElementById('events');
            eventsDiv.innerHTML = '';
            for (const [key, value] of Object.entries(receivedEvents)) {
                const entry = document.createElement('div');
                entry.className = 'success';
                entry.textContent = `${key}: ${JSON.stringify(value)}`;
                eventsDiv.appendChild(entry);
            }
        }
        
        // Auto-connect on page load
        window.addEventListener('load', () => {
            log('Page loaded. Ready to test WebSocket connection.');
            log('Make sure backend is running: python app.py --drivers sim');
        });
    </script>
</body>
</html>
"""

class MyHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/':
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write(HTML_CONTENT.encode())
        else:
            super().do_GET()

if __name__ == '__main__':
    PORT = 8888
    Handler = MyHTTPRequestHandler
    
    print(f"Starting test server on http://localhost:{PORT}")
    print(f"Open http://localhost:{PORT} in your browser to test WebSocket connection")
    
    with socketserver.TCPServer(("", PORT), Handler) as httpd:
        print(f"Serving on port {PORT}...")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutdown")
