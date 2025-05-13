import docker
import uuid
from datetime import datetime
import bleach
import re
import io
import tarfile
import magic

class docker_manager:
    def __init__(self):
        self.client = docker.from_env()
        self.api_client = docker.APIClient(base_url='unix://var/run/docker.sock')

    def contains_invalid_chars(self, s):
        return bool(re.search(r'[^a-zA-Z0-9\-_]', s))

    def return_result(self, type_return, message):
        return {"result": type_return, "message": message}

    def find_container_by_logical_name(self, user_id: str, container_name: str):
        containers = self.client.containers.list(
            all=True,
            filters={"label": [f"user_id={user_id}", f"container_name={container_name}"]}
        )
        return containers[0] if containers else None

    def ensure_user_in_container(self, container, user_id):
        # Check if user exists inside container
        exit_code, _ = container.exec_run(f"id -u {user_id}", user="root")
        if exit_code != 0:
            # User doesn't exist, so create it without sudo and with /bin/false shell
            container.exec_run(f"useradd -U -m -s /bin/bash {user_id}", user="root")
            print(f"Created user '{user_id}' in container {container.name}")
        else:
            print(f"User '{user_id}' already exists in container {container.name}")

    def rebalance_user_container_memory(self, user_id: str, only_running=True):
        containers = self.client.containers.list(
            all=not only_running,
            filters={"label": f"user_id={user_id}"}
        )
        if not containers:
            return

        per_container_limit = int(1024 * 1024 * 1024 / len(containers))

        for container in containers:
            try:
                container.update(mem_limit=per_container_limit)
                print(f"Updated {container.name} to {per_container_limit} bytes")
            except docker.errors.APIError as e:
                print(f"Could not update {container.name}: {e.explanation}")

    def rebalance_user_container_cpu(self, user_id: str, only_running=True):
        containers = self.client.containers.list(
            all=not only_running,
            filters={"label": f"user_id={user_id}"}
        )
        if not containers:
            return

        num = len(containers)
        cpu_period = 100000  # Standard CFS period
        cpu_quota = int(cpu_period / num)  # Fair share of 1 CPU

        for container in containers:
            try:
                container.update(cpu_period=cpu_period, cpu_quota=cpu_quota)
                print(f"Updated CPU for {container.name} to {cpu_quota}/{cpu_period} (== {cpu_quota / cpu_period:.2f} CPUs)")
            except docker.errors.APIError as e:
                print(f"Failed to update CPU for {container.name}: {e.explanation}")

    def rebalace_all_containers(self, user_id: str, only_running=True):
        self.rebalance_user_container_memory(user_id, only_running)
        self.rebalance_user_container_cpu(user_id, only_running)

    def create_container(self, os_image: str, user_id: str, container_name: str):
        try:
            # Ensure user doesn't already have a container with this logical name
            container_name = bleach.clean(container_name)
            os_image = bleach.clean(os_image)

            if self.contains_invalid_chars(container_name):
                return self.return_result("error", "Name must only contain letters, numbers, dashes, and underscores.")

            if os_image not in ["ubuntu", "debian", "centos", "alpine"]:
                return self.return_result("error", f"Invalid OS image '{os_image}'. Supported images are: Ubuntu, Debian, CentOS, Alpine.")

            if container_name == "":
                return self.return_result("error", "Container name cannot be empty.")
            
            existing = self.find_container_by_logical_name(user_id, container_name)
            if existing:
                return self.return_result("error", f"Container with name '{container_name}' already exists for user {user_id}.")

            unique_id = str(uuid.uuid4())
            docker_name = f"{unique_id}"
            container = self.client.containers.run(
                image=os_image,
                name=docker_name,
                detach=True,
                labels={
                    "user_id": user_id,
                    "container_name": container_name,
                    "uid": unique_id
                },
                tty=True
            )
            
            self.ensure_user_in_container(container, user_id)

            return self.return_result("success", f"Container '{container_name}' created for user {user_id}.")
        except docker.errors.ImageNotFound:
            return self.return_result("error", f"Image '{os_image}' not found.")
        except docker.errors.APIError as e:
            return self.return_result("error", f"Docker API error: {e.explanation}")

    def get_containers_by_user(self, user_id: str):
        try:
            containers = self.client.containers.list(all=True, filters={"label": f"user_id={user_id}"})
            container_list = []
            for c in containers:
                c.reload()
                info = c.attrs
                state = info.get("State", {})
                created = datetime.strptime(info["Created"][:19], "%Y-%m-%dT%H:%M:%S")
                started_at = state.get("StartedAt")
                last_started = (
                    datetime.strptime(started_at[:19], "%Y-%m-%dT%H:%M:%S").isoformat()
                    if started_at and started_at != "0001-01-01T00:00:00Z"
                    else None
                )
                container_list.append({
                    "id": c.id,
                    "name": c.labels.get("container_name", "unknown"),
                    "status": c.status,
                    "image": c.image.tags[0] if c.image.tags else "unknown",
                    "os": c.image.attrs.get("Os", "unknown"),
                    "created": created.isoformat(),
                    "last_started": last_started,
                    "running": c.status == "running"
                })
            return self.return_result("success", container_list)
        except docker.errors.APIError as e:
            return self.return_result("error", f"Docker API error: {e.explanation}")

    def start_container_by_name(self, user_id: str, container_name: str):
        try:
            container = self.find_container_by_logical_name(user_id, container_name)
            if not container:
                return self.return_result("error", f"No container named '{container_name}' found for user {user_id}.")

            container.reload()
            if container.status != "running":
                container.start()
                return self.return_result("success", f"Started container: {container_name}")
            else:
                return self.return_result("success", f"Container {container_name} is already running.")
        except docker.errors.APIError as e:
            return self.return_result("error", f"Docker API error: {e.explanation}")

    def stop_container_by_name(self, user_id: str, container_name: str):
        try:
            container = self.find_container_by_logical_name(user_id, container_name)
            if not container:
                return self.return_result("error", f"No container named '{container_name}' found for user {user_id}.")

            container.reload()
            if container.status == "running":
                container.stop()
                return self.return_result("success", f"Stopped container: {container_name}")
            else:
                return self.return_result("success", f"Container {container_name} is already stopped.")
        except docker.errors.APIError as e:
            return self.return_result("error", f"Docker API error: {e.explanation}")

    def delete_container_by_name(self, user_id: str, container_name: str):
        try:
            container = self.find_container_by_logical_name(user_id, container_name)
            if not container:
                return self.return_result("error", f"Container '{container_name}' not found.")
            container.remove(force=True)
            return self.return_result("success", f"Container '{container_name}' deleted.")
        except Exception as e:
            return self.return_result("error", str(e))

    def list_files(self, user_id: str, container_name: str):
        if not user_id or not container_name:
            return {"result": "error", "message": "Missing user or container info."}

        container = self.find_container_by_logical_name(user_id, container_name)
        if not container:
            return {"result": "error", "message": f"Container '{container_name}' not found."}

        try:
            # Run ls -p to mark directories with '/'
            exec_result = container.exec_run(
                cmd=f"ls -p /home/{user_id}",
                user=user_id
            )
            output = exec_result.output.decode("utf-8")
            files = [line for line in output.splitlines() if line.strip()]

            return {
                "files": files,
                "container_name": container_name
            }
        except Exception as e:
            return {
                "files": [],
                "error": str(e),
                "container_name": container_name   
            }

    def read_file(self, user_id: str, container_name: str, file_path: str):
        if not user_id or not container_name or not file_path:
            return {
                "error": "Missing required fields.",
                "file_path": file_path
            }

        container = self.find_container_by_logical_name(user_id, container_name)
        if not container:
            return {
                "error": "Container not found.",
                "file_path": file_path
            }

        try:
            full_path = f"/home/{user_id}/{file_path}"
            stream, _ = container.get_archive(full_path)

            tar_bytes = io.BytesIO(b''.join(stream))
            with tarfile.open(fileobj=tar_bytes) as tar:
                member = tar.getmember(file_path)
                file_obj = tar.extractfile(member)
                content_bytes = file_obj.read()

            mime = magic.from_buffer(content_bytes, mime=True)

            return {
                "file_path": file_path,
                "mime_type": mime,
                "content": content_bytes.decode("utf-8", errors="replace")
            }
        except KeyError:
            return {
                "error": "File not found in archive.",
                "file_path": file_path
            }
        except Exception as e:
            return {
                "error": str(e),
                "file_path": file_path
            }

    def write_file(self, user_id: str, container_name: str, file_path: str, content: str):
        container = self.find_container_by_logical_name(user_id, container_name)
        if not container:
            raise Exception("Container not found.")

        # File path inside the container
        target_path = f"/home/{user_id}"
        full_path = f"{target_path}/{file_path}"

        # Create a tar archive in memory with the file
        tarstream = io.BytesIO()
        with tarfile.open(fileobj=tarstream, mode='w') as tar:
            data = content.encode("utf-8")
            tarinfo = tarfile.TarInfo(name=file_path)
            tarinfo.size = len(data)
            tar.addfile(tarinfo, io.BytesIO(data))
        tarstream.seek(0)

        # Upload the archive to the target path
        success = container.put_archive(target_path, tarstream)

        if not success:
            raise Exception(f"Failed to write file to container at {full_path}")

    def delete_file(self, user_id: str, container_name: str, file_path: str):
        container = self.find_container_by_logical_name(user_id, container_name)
        if not container:
            return {"error": "Container not found"}

        try:
            exec_result = container.exec_run(
                f"rm -rf '{file_path}'",
                workdir=f"/home/{user_id}",
                demux=True
            )
            stdout, stderr = exec_result.output if exec_result.output else (b"", b"")
            if exec_result.exit_code != 0:
                return {"error": stderr.decode() if stderr else "Unknown error"}
            return {"result": "success"}
        except Exception as e:
            return {"error": str(e)}

    def create_folder(self, user_id: str, container_name: str, folder_path: str):
        container = self.find_container_by_logical_name(user_id, container_name)
        if not container:
            raise Exception("Container not found")
        command = f"mkdir -p /home/{user_id}/{folder_path}"
        exit_code, _ = container.exec_run(cmd=command)
        if exit_code != 0:
            raise Exception(f"Failed to create folder: {folder_path}")
