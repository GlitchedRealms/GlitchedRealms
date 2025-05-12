function getAceModeFromMime(mime) {
    const mimeMap = {
      "text/x-python": "ace/mode/python",
      "text/x-shellscript": "ace/mode/sh",
      "text/x-c": "ace/mode/c_cpp",
      "text/x-c++": "ace/mode/c_cpp",
      "application/javascript": "ace/mode/javascript",
      "text/html": "ace/mode/html",
      "text/css": "ace/mode/css",
      "application/json": "ace/mode/json",
      "application/x-httpd-php": "ace/mode/php",
      "text/x-java-source": "ace/mode/java",
      "text/markdown": "ace/mode/markdown",
      "application/xml": "ace/mode/xml",
    };
  
    return mimeMap[mime] || null;
  }

function getAceModeFromFilename(filename) {
    const lowerName = filename.toLowerCase();
  
    // Extensionless known files
    if (lowerName === "makefile") return "ace/mode/makefile";
    if (lowerName === "dockerfile") return "ace/mode/dockerfile";
    if (lowerName.endsWith("rc")) return "ace/mode/sh"; // e.g. .bashrc, .zshrc
  
    const parts = filename.split('.');
    if (parts.length > 1) {
      const ext = parts.pop().toLowerCase();
      const modeMap = {
        js: "ace/mode/javascript",
        jsx: "ace/mode/jsx",
        ts: "ace/mode/typescript",
        tsx: "ace/mode/tsx",
        py: "ace/mode/python",
        rb: "ace/mode/ruby",
        java: "ace/mode/java",
        c: "ace/mode/c_cpp",
        cpp: "ace/mode/c_cpp",
        h: "ace/mode/c_cpp",
        cs: "ace/mode/csharp",
        php: "ace/mode/php",
        html: "ace/mode/html",
        htm: "ace/mode/html",
        css: "ace/mode/css",
        scss: "ace/mode/scss",
        less: "ace/mode/less",
        sh: "ace/mode/sh",
        bash: "ace/mode/sh",
        zsh: "ace/mode/sh",
        json: "ace/mode/json",
        yaml: "ace/mode/yaml",
        yml: "ace/mode/yaml",
        xml: "ace/mode/xml",
        md: "ace/mode/markdown",
        txt: "ace/mode/text",
        sql: "ace/mode/sql",
        dockerfile: "ace/mode/dockerfile",
        makefile: "ace/mode/makefile",
        ini: "ace/mode/ini",
        toml: "ace/mode/toml",
        vue: "ace/mode/vue",
        go: "ace/mode/golang",
        rs: "ace/mode/rust",
        swift: "ace/mode/swift",
        kt: "ace/mode/kotlin",
        dart: "ace/mode/dart",
        lua: "ace/mode/lua",
        perl: "ace/mode/perl",
        pl: "ace/mode/perl",
        r: "ace/mode/r",
        scala: "ace/mode/scala",
        groovy: "ace/mode/groovy",
        asm: "ace/mode/assembly_x86",
        log: "ace/mode/log",
        conf: "ace/mode/conf",
        env: "ace/mode/sh",
        bat: "ace/mode/batchfile",
        ps1: "ace/mode/powershell"
      };
  
      return modeMap[ext] || "ace/mode/text";
    }
  
    // Fallback
    return "ace/mode/text";
  }
  