# RPM Spec file for Gerrit Review MCP Server
# System-wide installation with dedicated virtual environment

%define debug_package %{nil}
%define _python python3.12
%define install_dir /opt/gerrit-review-mcp
%define source_dir %{name}-%{version}

Name:           gerrit-review-mcp
Version:        0.1.0
Release:        1%{?dist}
Summary:        MCP server for Gerrit Code Review integration

License:        MIT
URL:            https://github.com/olssone/gerrit-mcp
Source0:        %{name}-%{version}.tar.gz

BuildArch:      x86_64
BuildRequires:  python3.12
BuildRequires:  python3.12-pip
Requires:       python3.12

%description
MCP (Model Context Protocol) server for Gerrit Code Review integration.
Provides tools for fetching changes, comparing patchsets, and submitting reviews.
Installed as a system-wide service with isolated Python dependencies.

This package uses Python 3.12 to meet the minimum requirement of Python 3.10+.

%prep
%setup -q -n %{source_dir}

%build
# Create virtual environment using Python 3.12
%{_python} -m venv %{_builddir}/venv

# Activate venv and install package with dependencies
%{_builddir}/venv/bin/pip install --upgrade pip setuptools wheel
%{_builddir}/venv/bin/pip install .

# Compile Python bytecode
%{_builddir}/venv/bin/python -m compileall %{_builddir}/venv/lib/

%install
# Create installation directories
mkdir -p %{buildroot}%{install_dir}/{bin,share/examples}
mkdir -p %{buildroot}%{_bindir}
mkdir -p %{buildroot}%{_docdir}/%{name}

# Copy virtual environment
cp -a %{_builddir}/venv %{buildroot}%{install_dir}/

# Fix hardcoded shebangs in venv scripts
# Replace BUILD directory paths with final installation paths
find %{buildroot}%{install_dir}/venv/bin -type f -exec sed -i \
  "s|#!%{_builddir}/venv/bin/python.*|#!/usr/bin/env python3|g" {} \;

# Install wrapper script — delegates to the installed console script
cat > %{buildroot}%{install_dir}/bin/%{name} << 'EOF'
#!/bin/bash
# Gerrit Review MCP Server Wrapper
# Delegates to the console script installed by pip into the venv

INSTALL_DIR="%{install_dir}"
CONSOLE_SCRIPT="${INSTALL_DIR}/venv/bin/gerrit-review-mcp"

if [ -f "$CONSOLE_SCRIPT" ]; then
  exec "${CONSOLE_SCRIPT}" "$@"
else
  echo "Error: gerrit-review-mcp console script not found at ${CONSOLE_SCRIPT}" >&2
  echo "Verify the package was installed correctly: ${INSTALL_DIR}/venv/bin/pip show gerrit-review-mcp" >&2
  exit 1
fi
EOF

chmod 755 %{buildroot}%{install_dir}/bin/%{name}

# Create symlink in /usr/bin
ln -s %{install_dir}/bin/%{name} %{buildroot}%{_bindir}/%{name}

# Install documentation
install -m 644 README.md %{buildroot}%{_docdir}/%{name}/
[ -f LICENSE ] && install -m 644 LICENSE %{buildroot}%{_docdir}/%{name}/

# Create example MCP configuration
cat > %{buildroot}%{install_dir}/share/examples/mcp-config.json << 'EOF'
{
  "mcpServers": {
    "gerrit-review-mcp": {
      "command": "gerrit-review-mcp",
      "args": [],
      "env": {
        "GERRIT_HOST": "gerrit.example.com",
        "GERRIT_USER": "your-username",
        "GERRIT_HTTP_PASSWORD": "your-http-password",
        "GERRIT_EXCLUDED_PATTERNS": "\\.pbxproj$,\\.xcworkspace$,node_modules/"
      },
      "alwaysAllow": [
        "fetch_gerrit_change",
        "fetch_patchset_diff",
        "submit_gerrit_review"
      ]
    }
  }
}
EOF

%files
%defattr(-,root,root,-)
%{install_dir}/
%{_bindir}/%{name}
%doc %{_docdir}/%{name}/

%post
echo "=========================================="
echo "Gerrit Review MCP Server installed successfully!"
echo ""
echo "Installation location: %{install_dir}"
echo "Command: %{name}"
PY_VER=$(%{install_dir}/venv/bin/python --version 2>/dev/null || echo "unknown")
echo "Python version: ${PY_VER}"
echo ""
echo "To configure, add to your Roo Code MCP settings file:"
echo "  ~/.roo/mcp.json or update global MCP config"
echo ""
echo "Example configuration:"
echo "  %{install_dir}/share/examples/mcp-config.json"
echo ""
echo "Test installation:"
echo "  %{name}"
echo "=========================================="

%preun
if [ $1 -eq 0 ]; then
  echo "Removing Gerrit Review MCP Server..."
fi

%postun
if [ $1 -eq 0 ]; then
  echo "Gerrit Review MCP Server removed."
fi
