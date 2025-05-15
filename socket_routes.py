from flask import session, request
from flask_socketio import disconnect
import threading
import select
import docker
import base64

terminal_sessions = {}

def register_socket_routes(socketio, docker_mgr):
    @socketio.on("connect")
    def on_connect():
        user_id = session.get("user_id")
        if user_id:
            print(f"User {user_id} connected")
        else:
            print("Unauthenticated user tried to connect, disconnecting.")
            disconnect()

    @socketio.on("disconnect")
    def on_disconnect():
        print("User disconnected")

    @socketio.on("request_devices")
    def request_devices(data):
        user_id = session.get("user_id")
        if not user_id:
            return {"result": "error", "message": "User not authenticated"}
        return docker_mgr.get_containers_by_user(user_id)

    @socketio.on("create_container")
    def create_container(data):
        user_id = session.get("user_id")
        if not user_id:
            return {"result": "error", "message": "User not authenticated"}
        return docker_mgr.create_container(
            data.get("os_image"),
            user_id,
            data.get("container_name"),
            data.get("template_type"),
        )

    @socketio.on("start_container")
    def start_container(data):
        user_id = session.get("user_id")
        if not user_id:
            return {"result": "error", "message": "User not authenticated"}
        return docker_mgr.start_container_by_name(user_id, data.get("container_name"))

    @socketio.on("stop_container")
    def stop_container(data):
        user_id = session.get("user_id")
        if not user_id:
            return {"result": "error", "message": "User not authenticated"}
        return docker_mgr.stop_container_by_name(user_id, data.get("container_name"))

    @socketio.on("delete_container")
    def delete_container(data):
        user_id = session.get("user_id")
        if not user_id:
            return {"result": "error", "message": "User not authenticated"}
        return docker_mgr.delete_container_by_name(user_id, data.get("container_name"))


    @socketio.on('terminal_input')
    def handle_terminal_input(data):
        user_id = session.get("user_id")
        container_name = data.get("container_name")
        tab_id = data.get("tab_id")
        input_data = data.get("input")
        sid = request.sid
        session_key = f"{sid}:{tab_id}"

        container = docker_mgr.find_container_by_logical_name(user_id, container_name)
        if not container:
            socketio.emit('terminal_output', {'output': 'Error: Container not found.'}, to=sid)
            return

        if session_key not in terminal_sessions:
            try:
                exec_id = docker_mgr.api_client.exec_create(
                    container.id,
                    cmd="/bin/bash",
                    tty=True,
                    stdin=True,
                    user=user_id,
                    workdir=f"/home/{user_id}"
                )["Id"]


                sock = docker_mgr.api_client.exec_start(
                    exec_id,
                    tty=True,
                    stream=False,
                    detach=False,
                    socket=True
                )._sock

                terminal_sessions[session_key] = sock

                def stream_output(sock, sid, tab_id):
                    try:
                        while True:
                            rlist, _, _ = select.select([sock], [], [], 0.1)
                            if rlist:
                                output = sock.recv(1024)
                                if not output:
                                    break
                                socketio.emit("terminal_output", {
                                    "output": output.decode(errors="ignore"),
                                    "tab_id": tab_id
                                }, to=sid)
                    except Exception as e:
                        print(f"Stream error: {e}")

                threading.Thread(target=stream_output, args=(sock, sid, tab_id), daemon=True).start()

            except Exception as e:
                print(f"Terminal setup error: {e}")
                socketio.emit("terminal_output", {
                    "output": f"Terminal setup error: {str(e)}",
                    "tab_id": tab_id
                }, to=sid)
                return

        try:
            terminal_sessions[session_key].send(input_data.encode())
        except Exception as e:
            print(f"Send error: {e}")
            socketio.emit("terminal_output", {
                "output": f"Send error: {str(e)}",
                "tab_id": tab_id
            }, to=sid)

    @socketio.on('disconnect')
    def handle_disconnect():
        sid = request.sid
        print(f"Client {sid} disconnected. Cleaning up terminals.")
        for key in list(terminal_sessions.keys()):
            if key.startswith(f"{sid}:"):
                try:
                    terminal_sessions[key].close()
                except Exception:
                    pass
                del terminal_sessions[key]

    @socketio.on("list_files")
    def list_files(data):
        user_id = session.get("user_id")
        container_name = data.get("container_name")
        sid = request.sid

        socketio.emit("file_list", docker_mgr.list_files(user_id, container_name), to=sid)

    @socketio.on("read_file")
    def read_file(data):
        user_id = session.get("user_id")
        container_name = data.get("container_name")
        file_path = data.get("file_path")
        sid = request.sid

        socketio.emit("file_content", docker_mgr.read_file(user_id, container_name, file_path), to=sid)

    @socketio.on("file_edit")
    def handle_file_edit(data):
        user_id = session.get("user_id")
        container_name = data.get("container_name")
        file_path = data.get("file_path")
        content = data.get("content")
        sid = request.sid

        if not user_id:
            socketio.emit("file_edit_error", {"error": "User not authenticated."}, to=sid)
            return

        if not container_name or not file_path or content is None:
            socketio.emit("file_edit_error", {"error": "Missing required data."}, to=sid)
            return

        try:
            docker_mgr.write_file(user_id, container_name, file_path, content)
            # Optional: confirm success to the client
            socketio.emit("file_saved", {"file_path": file_path}, to=sid)
        except Exception as e:
            socketio.emit("file_edit_error", {
                "error": str(e),
                "file_path": file_path
            }, to=sid)

    @socketio.on("download_file")
    def handle_download_file(data):
        user_id = session.get("user_id")
        container_name = data.get("container_name")
        file_path = data.get("file_path")
        sid = request.sid

        if not user_id or not container_name or not file_path:
            socketio.emit("download_error", {
                "file_path": file_path,
                "error": "Missing required fields or not authenticated."
            }, to=sid)
            return

        try:
            # Use your existing Docker manager to read file contents
            result = docker_mgr.read_file(user_id, container_name, file_path)

            if result.get("error"):
                socketio.emit("download_error", {
                    "file_path": file_path,
                    "error": result["error"]
                }, to=sid)
                return

            # Encode file content as base64 to safely send binary data over socket
            content = result.get("content", "")
            encoded_content = base64.b64encode(content.encode("latin1")).decode("ascii")

            socketio.emit("download_file_response", {
                "file_path": file_path,
                "filename": file_path.split("/")[-1],
                "content": encoded_content
            }, to=sid)

        except Exception as e:
            socketio.emit("download_error", {
                "file_path": file_path,
                "error": str(e)
            }, to=sid)
            
    @socketio.on("delete_file")
    def handle_delete_file(data):
        user_id = session.get("user_id")
        container_name = data.get("container_name")
        file_path = data.get("file_path")
        sid = request.sid

        if not user_id or not container_name or not file_path:
            socketio.emit("delete_error", {
                "file_path": file_path,
                "error": "Missing required fields or not authenticated."
            }, to=sid)
            return

        try:
            result = docker_mgr.delete_file(user_id, container_name, file_path)
            if result.get("error"):
                socketio.emit("delete_error", {
                    "file_path": file_path,
                    "error": result["error"]
                }, to=sid)
                return

            socketio.emit("file_deleted", {
                "file_path": file_path
            }, to=sid)

            # Optional: Refresh the file list
            socketio.emit("file_list", docker_mgr.list_files(user_id, container_name), to=sid)

        except Exception as e:
            socketio.emit("delete_error", {
                "file_path": file_path,
                "error": str(e)
            }, to=sid)

    @socketio.on("create_file")
    def handle_create_file(data):
        user_id = session.get("user_id")
        container_name = data.get("container_name")
        file_path = data.get("file_path")
        sid = request.sid

        if not user_id or not container_name or not file_path:
            socketio.emit("file_create_error", {
                "error": "Missing required data",
                "file_path": file_path
            }, to=sid)
            return

        try:
            docker_mgr.write_file(user_id, container_name, file_path, "")
            socketio.emit("file_created", {
                "file_path": file_path
            }, to=sid)
            # Optionally refresh the file list
            socketio.emit("file_list", docker_mgr.list_files(user_id, container_name), to=sid)
        except Exception as e:
            socketio.emit("file_create_error", {
                "error": str(e),
                "file_path": file_path
            }, to=sid)

    @socketio.on("create_folder")
    def handle_create_folder(data):
        user_id = session.get("user_id")
        container_name = data.get("container_name")
        folder_path = data.get("folder_path")
        sid = request.sid

        if not user_id or not container_name or not folder_path:
            socketio.emit("folder_create_error", {
                "error": "Missing required data",
                "folder_path": folder_path
            }, to=sid)
            return

        try:
            docker_mgr.create_folder(user_id, container_name, folder_path)
            socketio.emit("folder_created", {
                "folder_path": folder_path
            }, to=sid)
            socketio.emit("file_list", docker_mgr.list_files(user_id, container_name), to=sid)
        except Exception as e:
            socketio.emit("folder_create_error", {
                "error": str(e),
                "folder_path": folder_path
            }, to=sid)

