#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
BUILD_DIR="${PROJECT_DIR}/rpm_build"

# Print message to standard output: 🧹 Preparing build directories...
echo "🧹 Preparing build directories..."
rm -rf "${BUILD_DIR}"
mkdir -p "${BUILD_DIR}"/{BUILD,RPMS,SOURCES,SPECS,SRPMS}

# Print message to standard output: 📦 Packaging source archive...
echo "📦 Packaging source archive..."
# Copy workspace source files to the SOURCES directory
cp -r "${PROJECT_DIR}"/src "${BUILD_DIR}/SOURCES/"
cp -r "${PROJECT_DIR}"/frontend "${BUILD_DIR}/SOURCES/"
cp -r "${PROJECT_DIR}"/assets "${BUILD_DIR}/SOURCES/"
cp -r "${PROJECT_DIR}"/custom_voice_models "${BUILD_DIR}/SOURCES/"
cp "${PROJECT_DIR}"/*.py "${BUILD_DIR}/SOURCES/"
cp "${PROJECT_DIR}"/requirements*.txt "${BUILD_DIR}/SOURCES/"
cp "${PROJECT_DIR}"/LICENSE "${BUILD_DIR}/SOURCES/"
cp "${PROJECT_DIR}"/.env "${BUILD_DIR}/SOURCES/" 2>/dev/null || true
cp "${PROJECT_DIR}/Julius Logo.png" "${BUILD_DIR}/SOURCES/julius.png"

# Copy script templates to sources
mkdir -p "${BUILD_DIR}/SOURCES/scripts"
cp "${PROJECT_DIR}/scripts/julius-cli.sh" "${BUILD_DIR}/SOURCES/scripts/"
cp "${PROJECT_DIR}/scripts/julius-gui.sh" "${BUILD_DIR}/SOURCES/scripts/"
cp "${PROJECT_DIR}/scripts/juliusd.service" "${BUILD_DIR}/SOURCES/scripts/"
cp "${PROJECT_DIR}/scripts/julius-gui.desktop" "${BUILD_DIR}/SOURCES/scripts/"

# Print message to standard output: 📝 Copying spec file...
echo "📝 Copying spec file..."
cp "${PROJECT_DIR}/julius.spec" "${BUILD_DIR}/SPECS/"

# Print message to standard output: 🛠 Building RPM package...
echo "🛠 Building RPM package..."
# Execute command: rpmbuild --define "_topdir ${BUILD_DIR}" -bb "${BUILD_DIR}/SPECS/julius.spec"
rpmbuild --define "_topdir ${BUILD_DIR}" -bb "${BUILD_DIR}/SPECS/julius.spec"

# Print message to standard output: 🎉 RPM package built successfully!
echo "🎉 RPM package built successfully!"
cp "${BUILD_DIR}/RPMS/noarch"/*.rpm "${PROJECT_DIR}/"
# Print message to standard output: Output: ${PROJECT_DIR}/julius-agent-1.0.0-1.noarch.rpm
echo "Output: ${PROJECT_DIR}/julius-agent-1.0.0-1.noarch.rpm"
