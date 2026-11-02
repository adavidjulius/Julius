#!/bin/bash
set -e

# Install Tuist via Homebrew
brew tap tuist/tuist
brew install --formula tuist

# Generate Xcode project
cd ../
tuist install
tuist generate
