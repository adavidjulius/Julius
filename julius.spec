Name:           julius-agent
Version:        1.0.0
Release:        1%{?dist}
Summary:        Autonomous Web Agent (Julius)
License:        MIT
URL:            https://github.com/JuliusAgent/Julius
BuildArch:      noarch

# Core Fedora package dependencies
Requires:       python3
Requires:       python3-pip
Requires:       python3-virtualenv
Requires:       portaudio
Requires:       systemd

%description
An autonomous web agent and helper that executes coding tasks, handles undos, and runs tests.

%install
# Create directories
mkdir -p %{buildroot}/opt/julius
mkdir -p %{buildroot}/usr/bin
mkdir -p %{buildroot}/usr/lib/systemd/system
mkdir -p %{buildroot}/usr/share/applications
mkdir -p %{buildroot}/usr/share/pixmaps

# Copy code and resources
cp -r %{_sourcedir}/src %{buildroot}/opt/julius/
cp -r %{_sourcedir}/frontend %{buildroot}/opt/julius/
cp -r %{_sourcedir}/assets %{buildroot}/opt/julius/
cp -r %{_sourcedir}/custom_voice_models %{buildroot}/opt/julius/
cp %{_sourcedir}/*.py %{buildroot}/opt/julius/
cp %{_sourcedir}/requirements*.txt %{buildroot}/opt/julius/
cp %{_sourcedir}/LICENSE %{buildroot}/opt/julius/
cp %{_sourcedir}/.env %{buildroot}/opt/julius/ || true

# Copy wrapper scripts and service file
cp %{_sourcedir}/scripts/julius-cli.sh %{buildroot}/usr/bin/julius
cp %{_sourcedir}/scripts/julius-gui.sh %{buildroot}/usr/bin/julius-gui
cp %{_sourcedir}/scripts/juliusd.service %{buildroot}/usr/lib/systemd/system/juliusd.service

# Desktop integration & custom icon
cp %{_sourcedir}/scripts/julius-gui.desktop %{buildroot}/usr/share/applications/julius-gui.desktop
cp %{_sourcedir}/julius.png %{buildroot}/usr/share/pixmaps/julius.png 2>/dev/null || true

%post
# Update desktop database
update-desktop-database &> /dev/null || :

# Always exit 0 to prevent RPM transaction failures
exit 0

%preun
if [ $1 -eq 0 ]; then
    systemctl stop juliusd || true
    systemctl disable juliusd || true
fi

%postun
if [ $1 -eq 0 ]; then
    rm -rf /opt/julius
    rm -f /usr/bin/julius
    rm -f /usr/bin/julius-gui
    rm -f /usr/lib/systemd/system/juliusd.service
    rm -f /usr/share/applications/julius-gui.desktop
    rm -f /usr/share/pixmaps/julius.png
    systemctl daemon-reload || true
    update-desktop-database &> /dev/null || :
fi

%files
/opt/julius/
%attr(0755, root, root) /usr/bin/julius
%attr(0755, root, root) /usr/bin/julius-gui
/usr/lib/systemd/system/juliusd.service
/usr/share/applications/julius-gui.desktop
