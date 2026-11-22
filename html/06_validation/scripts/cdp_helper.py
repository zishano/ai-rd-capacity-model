"""Small dependency-free Chrome DevTools client for local dashboard QA."""
from __future__ import annotations

import base64
import json
import os
import shutil
import signal
import socket
import struct
import subprocess
import tempfile
import time
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import urlopen


class Chrome:
    def __init__(self, timeout=45):
        self.deadline=time.monotonic()+timeout
        self.temp=tempfile.TemporaryDirectory(prefix="team_dashboard_chrome_",dir="/tmp")
        self.profile=Path(self.temp.name)
        self.log=(self.profile/"chrome_stderr.log").open("w")
        executable=shutil.which("google-chrome") or shutil.which("chromium")
        if not executable:raise RuntimeError("No existing Chrome executable")
        self.process=subprocess.Popen([executable,"--headless","--no-sandbox","--disable-gpu",
            "--disable-dev-shm-usage","--disable-background-networking","--no-first-run",
            "--no-default-browser-check","--remote-debugging-port=0","--remote-allow-origins=*",
            "--user-data-dir="+str(self.profile),"about:blank"],stdout=subprocess.DEVNULL,
            stderr=self.log,start_new_session=True)
        port_file=self.profile/"DevToolsActivePort"
        while not port_file.exists():
            if self.process.poll() is not None:raise RuntimeError("Chrome exited before opening DevTools")
            self.remaining();time.sleep(.05)
        port=port_file.read_text().splitlines()[0]
        with urlopen("http://127.0.0.1:"+port+"/json/list",timeout=self.remaining()) as response:
            targets=json.load(response)
        page=next(target for target in targets if target["type"]=="page")
        address=urlsplit(page["webSocketDebuggerUrl"])
        self.sock=socket.create_connection((address.hostname,address.port),timeout=self.remaining())
        self.buffer=b""
        key=base64.b64encode(os.urandom(16)).decode()
        self.sock.sendall((f"GET {address.path} HTTP/1.1\r\nHost: {address.netloc}\r\n"
            f"Upgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n\r\n").encode())
        while b"\r\n\r\n" not in self.buffer:
            self.buffer+=self.sock.recv(65536)
        headers,self.buffer=self.buffer.split(b"\r\n\r\n",1)
        if b" 101 " not in headers.split(b"\r\n",1)[0]:raise RuntimeError("CDP WebSocket handshake rejected")
        self.sequence=0
        self.events=[]
        self.contexts={}
        self.pending_sessions=[]
        self.sessions=set()
        self.call("Page.enable")
        self.call("Runtime.enable")
        self.call("Log.enable")
        self.call("Target.setAutoAttach",dict(autoAttach=True,waitForDebuggerOnStart=False,flatten=True))

    def remaining(self):
        seconds=self.deadline-time.monotonic()
        if seconds<=0:raise TimeoutError("Chrome QA exceeded the 45-second deadline")
        return seconds

    def _read(self,count):
        while len(self.buffer)<count:
            self.sock.settimeout(self.remaining())
            part=self.sock.recv(max(65536,count-len(self.buffer)))
            if not part:raise RuntimeError("Chrome closed its DevTools connection")
            self.buffer+=part
        result,self.buffer=self.buffer[:count],self.buffer[count:]
        return result

    def _send(self,payload,opcode=1):
        mask=os.urandom(4)
        length=len(payload)
        head=bytes([0x80|opcode])
        head+=bytes([0x80|length]) if length<126 else bytes([0x80|126])+struct.pack("!H",length) if length<65536 else bytes([0x80|127])+struct.pack("!Q",length)
        self.sock.sendall(head+mask+bytes(value^mask[i%4] for i,value in enumerate(payload)))

    def _receive(self):
        pieces=[]
        while True:
            first,second=self._read(2)
            length=second&127
            if length==126:length=struct.unpack("!H",self._read(2))[0]
            elif length==127:length=struct.unpack("!Q",self._read(8))[0]
            mask=self._read(4) if second&128 else None
            payload=self._read(length)
            if mask:payload=bytes(v^mask[i%4] for i,v in enumerate(payload))
            opcode=first&15
            if opcode==8:raise RuntimeError("CDP WebSocket closed")
            if opcode==9:self._send(payload,10);continue
            if opcode==10:continue
            pieces.append(payload)
            if first&128:return json.loads(b"".join(pieces))

    def call(self,method,params=None,session=None):
        self.remaining();self.sequence+=1
        request_id=self.sequence
        request=dict(id=request_id,method=method,params=params or {})
        if session is not None:request["sessionId"]=session
        self._send(json.dumps(request).encode())
        while True:
            message=self._receive()
            if message.get("id")==request_id:
                if "error" in message:raise RuntimeError(f"{method}: {message['error']}")
                return message.get("result",{})
            self.events.append(message)
            event_session=message.get("sessionId")
            if message.get("method")=="Runtime.executionContextCreated":
                context=message["params"]["context"];self.contexts[(event_session,context["id"])]=context
            elif message.get("method")=="Runtime.executionContextsCleared":
                self.contexts={key:value for key,value in self.contexts.items() if key[0]!=event_session}
            elif message.get("method")=="Runtime.executionContextDestroyed":
                self.contexts.pop((event_session,message["params"]["executionContextId"]),None)
            elif message.get("method")=="Target.attachedToTarget":
                attached=message["params"]["sessionId"]
                if attached not in self.sessions:self.pending_sessions.append(attached)

    def enable_attached(self):
        while self.pending_sessions:
            session=self.pending_sessions.pop(0)
            if session in self.sessions:continue
            self.sessions.add(session)
            self.call("Runtime.enable",session=session)
            self.call("Page.enable",session=session)
            self.call("Target.setAutoAttach",dict(autoAttach=True,waitForDebuggerOnStart=False,flatten=True),session)

    def evaluate(self,expression,context=None):
        params=dict(expression=expression,returnByValue=True,awaitPromise=True)
        session=None
        if isinstance(context,tuple):session,context=context
        if context is not None:params["contextId"]=context
        result=self.call("Runtime.evaluate",params,session)
        if result.get("exceptionDetails"):
            raise RuntimeError("Browser evaluation: "+json.dumps(result["exceptionDetails"],ensure_ascii=False))
        return result["result"].get("value")

    def screenshot(self,path,full_page=False):
        params=dict(format="png",captureBeyondViewport=full_page)
        if full_page:
            size=self.call("Page.getLayoutMetrics")["cssContentSize"]
            params["clip"]=dict(x=0,y=0,width=size["width"],height=size["height"],scale=1)
        path.write_bytes(base64.b64decode(self.call("Page.captureScreenshot",params)["data"]))

    def close(self):
        if hasattr(self,"sock"):
            self.sock.close()
        if hasattr(self,"process") and self.process.poll() is None:
            os.killpg(self.process.pid,signal.SIGTERM)
            try:self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:os.killpg(self.process.pid,signal.SIGKILL);self.process.wait()
        self.log.close()
        self.temp.cleanup()

    def __enter__(self):return self
    def __exit__(self,*args):self.close()
