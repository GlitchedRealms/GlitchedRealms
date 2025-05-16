const terminals = {};
let currentTabId = null;
const socket = io(); // Global socket connection
const editor = ace.edit("editor");

// Create terminal tab element
function createTerminalTab(id, label) {
  const tab = document.createElement("div");
  tab.classList.add("terminal-tab");
  tab.dataset.id = id;
  tab.innerHTML = `${label} <span class="close-btn" data-close="${id}">×</span>`;
  return tab;
}

// Create terminal instance and attach to DOM
function createTerminalInstance(id) {
  const instance = document.createElement("div");
  instance.classList.add("terminal-instance");
  instance.id = `terminal-${id}`;
  document.getElementById("terminalContainer").appendChild(instance);

  const term = new Terminal({ theme: { background: "#000", foreground: "#fff" }, fontSize: 14 });
  term.open(instance);

  socket.emit("terminal_input", {
    container_name: pathname,
    tab_id: id,
    input: "clear\n",
  });

  term.onData(data => {
    socket.emit("terminal_input", {
      container_name: pathname,
      tab_id: id,
      input: data,
    });

    setTimeout(() => loadFileList(pathname), 500);
  });

  terminals[id] = { term };
}

// Switch between terminal tabs
function switchToTab(id) {
  document.querySelectorAll(".terminal-tab").forEach(tab => {
    tab.classList.toggle("active", tab.dataset.id === id);
  });
  document.querySelectorAll(".terminal-instance").forEach(inst => {
    inst.classList.toggle("active", inst.id === `terminal-${id}`);
  });
  currentTabId = id;
  saveLayout();
}

// Add new terminal tab
function addTerminalTab(restoreId = null, restoreLabel = null) {
  const id = restoreId || String(Date.now());
  const label = restoreLabel || `Terminal ${Object.keys(terminals).length + 1}`;
  const tab = createTerminalTab(id, label);
  document.getElementById("terminalTabs").insertBefore(tab, document.getElementById("addTabBtn"));

  createTerminalInstance(id);
  switchToTab(id);
  saveLayout();
}

// Close terminal tab
function closeTab(id) {
  document.querySelector(`.terminal-tab[data-id='${id}']`)?.remove();
  document.getElementById(`terminal-${id}`)?.remove();
  delete terminals[id];

  if (currentTabId === id) {
    const first = document.querySelector(".terminal-tab");
    currentTabId = first ? first.dataset.id : null;
    if (first) switchToTab(first.dataset.id);
  }

  saveLayout();
}

// Save current layout to localStorage
function saveLayout() {
  const layout = {
    sidebarWidth: document.getElementById("sidebar").offsetWidth,
    editorHeight: document.getElementById("editor").offsetHeight,
    openTabs: Array.from(document.querySelectorAll(".terminal-tab")).map(tab => ({
      id: tab.dataset.id,
      label: tab.textContent.replace("×", "").trim()
    })),
    activeTabId: currentTabId
  };
  localStorage.setItem("layoutSettings", JSON.stringify(layout));
}

// Load layout from localStorage
function loadLayout() {
  const layout = JSON.parse(localStorage.getItem("layoutSettings"));
  if (!layout) return addTerminalTab();

  if (layout.sidebarWidth) document.getElementById("sidebar").style.width = `${layout.sidebarWidth}px`;
  if (layout.editorHeight) {
    const editorElem = document.getElementById("editor");
    editorElem.style.flex = "none";
    editorElem.style.height = `${layout.editorHeight}px`;
  }

  (layout.openTabs || []).forEach(tab => addTerminalTab(tab.id, tab.label));
  if (layout.activeTabId) switchToTab(layout.activeTabId);
}

function resetLayout() {
  localStorage.removeItem("layoutSettings");
  location.reload();
}

function loadFileList(containerName) {
  socket.emit("list_files", { container_name: containerName });
}

socket.on("file_list", data => {
  if (data.container_name !== pathname) return;

  const fileList = document.querySelector("#sidebar ul");
  fileList.innerHTML = "";

  if (data.error) {
    fileList.innerHTML = `<li>Error loading files: ${data.error}</li>`;
    return;
  }

  data.files.forEach(file => {
    const li = document.createElement("li");
    li.classList.add("file-item");

    const span = document.createElement("span");
    span.textContent = file;
    span.style.flex = "1";
    span.style.cursor = "pointer";

    const cleanFileName = file.replace(/\/$/, '');
    if (!file.endsWith("/")) {
      span.addEventListener("click", () => {
        socket.emit("read_file", {
          container_name: pathname,
          file_path: cleanFileName
        });
      });
    }

    const menuBtn = document.createElement("span");
    menuBtn.className = "menu-btn";
    menuBtn.textContent = "⋮";
    menuBtn.style.cursor = "pointer";

    const dropdown = document.createElement("div");
    dropdown.className = "dropdown-menu hidden";
    dropdown.innerHTML = `
      <div class="dropdown-item" data-action="download">Download</div>
      <div class="dropdown-item" data-action="delete">Delete</div>
    `;

    menuBtn.addEventListener("click", e => {
      e.stopPropagation();
      document.querySelectorAll(".dropdown-menu").forEach(menu => menu.classList.add("hidden"));
      dropdown.classList.toggle("hidden");
    });

    dropdown.addEventListener("click", e => {
      const action = e.target.dataset.action;
      if (action === "download") {
        socket.emit("download_file", { container_name: pathname, file_path: cleanFileName });
      } else if (action === "delete") {
        if (confirm(`Are you sure you want to delete "${cleanFileName}"?`)) {
          socket.emit("delete_file", { container_name: pathname, file_path: cleanFileName });
          editor.currentFile = null;
          editor.setValue("", -1);
        }
      }
      dropdown.classList.add("hidden");
    });

    li.appendChild(span);
    li.appendChild(menuBtn);
    li.appendChild(dropdown);
    fileList.appendChild(li);
  });
});

// Close all dropdowns on click
document.addEventListener("click", () => {
  document.querySelectorAll(".dropdown-menu, .file-menu-dropdown").forEach(menu => menu.classList.add("hidden"));
});

socket.on("download_file_response", ({ content, filename }) => {
  const binary = atob(content);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
  const blob = new Blob([bytes]);
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
});

socket.on("file_content", ({ error, content, file_path, mime_type }) => {
  if (error) return alert(`Error loading file "${file_path}": ${error}`);

  editor.setValue(content, -1);
  editor.currentFile = file_path;

  const mode = getAceModeFromMime(mime_type || "") || getAceModeFromFilename(file_path);
  editor.session.setMode(mode);
});

socket.on("terminal_output", ({ tab_id, output }) => {
  if (terminals[tab_id]) terminals[tab_id].term.write(output);
});

document.addEventListener("DOMContentLoaded", () => {
  const addBtn = document.createElement("div");
  addBtn.id = "addTabBtn";
  addBtn.textContent = "+";
  addBtn.style.cursor = "pointer";
  addBtn.style.padding = "8px 16px";
  document.getElementById("terminalTabs").appendChild(addBtn);

  document.getElementById("terminalTabs").addEventListener("click", e => {
    if (e.target.classList.contains("close-btn")) {
      closeTab(e.target.dataset.close);
    } else if (e.target.classList.contains("terminal-tab")) {
      switchToTab(e.target.dataset.id);
    } else if (e.target.id === "addTabBtn") {
      addTerminalTab();
    }
  });

  editor.setTheme("ace/theme/monokai");
  editor.session.setMode("ace/mode/sh");
  editor.setOptions({ fontSize: "14px", showPrintMargin: false });

  let lastSentContent = "";
  editor.session.on("change", () => {
    const content = editor.getValue();
    if (content !== lastSentContent && editor.currentFile) {
      lastSentContent = content;
      socket.emit("file_edit", {
        container_name: pathname,
        file_path: editor.currentFile,
        content: content
      });
    }
  });

  document.getElementById("resizeSidebar").addEventListener("mousedown", () => {
    const move = e => {
      document.getElementById("sidebar").style.width = `${e.clientX}px`;
      saveLayout();
    };
    document.addEventListener("mousemove", move);
    document.addEventListener("mouseup", () => document.removeEventListener("mousemove", move), { once: true });
  });

  document.getElementById("resizeTerminal").addEventListener("mousedown", () => {
    const move = e => {
      const editorElem = document.getElementById("editor");
      editorElem.style.flex = "none";
      editorElem.style.height = `${e.clientY - editorElem.getBoundingClientRect().top}px`;
      saveLayout();
    };
    document.addEventListener("mousemove", move);
    document.addEventListener("mouseup", () => document.removeEventListener("mousemove", move), { once: true });
  });

  loadLayout();
  loadFileList(pathname);
});

// File menu dropdown
const fileMenuBtn = document.querySelector(".file-menu-btn");
const fileMenuDropdown = document.querySelector(".file-menu-dropdown");

fileMenuBtn.addEventListener("click", e => {
  e.stopPropagation();
  document.querySelectorAll(".dropdown-menu, .file-menu-dropdown").forEach(menu => menu.classList.add("hidden"));
  fileMenuDropdown.classList.toggle("hidden");
});

fileMenuDropdown.addEventListener("click", e => {
  const action = e.target.dataset.action;
  if (action === "new_file" || action === "new_folder") {
    createInlineInput(action === "new_file" ? "file" : "folder");
  }
  fileMenuDropdown.classList.add("hidden");
});

// Inline input for new files/folders
function createInlineInput(type = "file") {
  const list = document.querySelector(".sidebar ul");
  const li = document.createElement("li");
  const input = document.createElement("input");
  input.type = "text";
  input.placeholder = type === "file" ? "New file name" : "New folder name";
  input.className = "inline-input";
  li.appendChild(input);
  list.appendChild(li);
  input.focus();

  function handleSubmit() {
    const name = input.value.trim();
    if (!name) {
      li.remove();
      return;
    }
    const payload = {
      container_name: pathname,
      [type === "file" ? "file_path" : "folder_path"]: name
    };
    socket.emit(type === "file" ? "create_file" : "create_folder", payload);
    li.remove();
  }

  input.addEventListener("blur", handleSubmit);
  input.addEventListener("keydown", e => {
    if (e.key === "Enter") handleSubmit();
    else if (e.key === "Escape") li.remove();
  });
}

// Mobile view tab switching
document.getElementById("tabEditor").addEventListener("click", () => {
  document.getElementById("editor").classList.add("active");
  document.querySelector(".terminal-section").classList.remove("active");
  document.getElementById("tabEditor").classList.add("active");
  document.getElementById("tabTerminal").classList.remove("active");
});

document.getElementById("tabTerminal").addEventListener("click", () => {
  document.getElementById("editor").classList.remove("active");
  document.querySelector(".terminal-section").classList.add("active");
  document.getElementById("tabEditor").classList.remove("active");
  document.getElementById("tabTerminal").classList.add("active");
});
