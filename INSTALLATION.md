# Installation Guide

Complete installation and setup guide for the Speak TTS command-line tool.

## Table of Contents

- [Quick Installation](#quick-installation)
- [Detailed Installation](#detailed-installation)
- [Configuration Setup](#configuration-setup)
- [Verification & Testing](#verification--testing)
- [Troubleshooting](#troubleshooting)

## Quick Installation

For experienced users who want a fast setup:

```bash
# 1. Clone repository (if not already cloned)
cd ~/
git clone https://github.com/triepod-ai/speak-app.git

# 2. Create ~/bin directory if it doesn't exist
mkdir -p ~/bin

# 3. Create symlinks for all speak commands
ln -sf ~/speak-app/speak ~/bin/speak
ln -sf ~/speak-app/speak-dev ~/bin/speak-dev
ln -sf ~/speak-app/speak-with-tracking ~/bin/speak-with-tracking

# 4. Add ~/bin to PATH and configure TTS in ~/.bash_aliases
cat >> ~/.bash_aliases << 'EOF'

# Add ~/bin to PATH
export PATH="$HOME/bin:$PATH"

# Speak App TTS Configuration - Cost Optimized
export TTS_PROVIDER=openai  # 22x cheaper than ElevenLabs
export OPENAI_API_KEY="your-openai-api-key-here"
export OPENAI_TTS_VOICE=onyx  # Best voice for notifications
export OPENAI_TTS_MODEL=tts-1  # Use tts-1-hd only when needed
export ELEVENLABS_API_KEY="your-elevenlabs-key-here"  # Backup provider
export ENGINEER_NAME="YourName"
export TTS_ENABLED=true
EOF

# 5. Reload configuration
source ~/.bash_aliases

# 6. Verify installation
speak --status
speak "Installation complete"
```

## Detailed Installation

### Prerequisites

Before installing, ensure you have:

- **Python 3.11 or higher**
  ```bash
  python3 --version
  ```

- **uv package manager** (for Python script execution)
  ```bash
  curl -LsSf https://astral.sh/uv/install.sh | sh
  ```

- **API Keys** (optional, but recommended):
  - OpenAI API key from [platform.openai.com/api-keys](https://platform.openai.com/api-keys)
  - ElevenLabs API key from [elevenlabs.io](https://elevenlabs.io) (for premium voices)

### Step 1: Clone Repository

```bash
# Navigate to your home directory
cd ~/

# Clone the repository
git clone https://github.com/triepod-ai/speak-app.git

# Navigate into the directory
cd speak-app

# Verify files are present
ls -la speak*
```

Expected output:
```
-rwxr-xr-x speak
-rwxr-xr-x speak-dev
-rwxr-xr-x speak-with-tracking
```

### Step 2: Create ~/bin Directory

The `~/bin` directory is a standard location for user-specific executables.

```bash
# Create the directory if it doesn't exist
mkdir -p ~/bin

# Verify it was created
ls -ld ~/bin
```

### Step 3: Create Symlinks

Create symbolic links in `~/bin` to make the speak commands globally accessible:

```bash
# Create symlinks for all speak commands
ln -sf ~/speak-app/speak ~/bin/speak
ln -sf ~/speak-app/speak-dev ~/bin/speak-dev
ln -sf ~/speak-app/speak-with-tracking ~/bin/speak-with-tracking

# Verify symlinks were created
ls -la ~/bin/speak*
```

Expected output:
```
lrwxrwxrwx speak -> /home/username/speak-app/speak
lrwxrwxrwx speak-dev -> /home/username/speak-app/speak-dev
lrwxrwxrwx speak-with-tracking -> /home/username/speak-app/speak-with-tracking
```

### Step 4: Add ~/bin to PATH

Add `~/bin` to your PATH so the shell can find the speak commands:

```bash
# Edit your ~/.bash_aliases file
nano ~/.bash_aliases
```

Add this line:
```bash
# Add ~/bin to PATH
export PATH="$HOME/bin:$PATH"
```

**Alternative**: Append automatically:
```bash
echo 'export PATH="$HOME/bin:$PATH"' >> ~/.bash_aliases
```

## Configuration Setup

### Method 1: Manual Configuration (Recommended)

Edit `~/.bash_aliases` to add TTS configuration:

```bash
nano ~/.bash_aliases
```

Add these lines:
```bash
# Speak App TTS Configuration - Cost Optimized
export TTS_ENABLED=true
export TTS_PROVIDER=openai  # 22x cheaper than ElevenLabs
export OPENAI_API_KEY="sk-proj-YOUR-KEY-HERE"
export OPENAI_TTS_VOICE=onyx  # Best voice for notifications
export OPENAI_TTS_MODEL=tts-1  # Use tts-1-hd only when needed
export ELEVENLABS_API_KEY="sk_YOUR-KEY-HERE"  # Backup provider
export ENGINEER_NAME="Your Name"
```

### Method 2: Using the Setup Script

The repository includes a setup script for OpenAI configuration:

```bash
cd ~/speak-app
./set_openai_default.py
```

This script will:
- Add OpenAI configuration to `~/.bash_aliases`
- Show cost comparison
- Verify API key presence
- Provide setup instructions

### Configuration Options Explained

| Variable | Purpose | Example Value |
|----------|---------|---------------|
| `TTS_ENABLED` | Enable/disable TTS globally | `true` or `false` |
| `TTS_PROVIDER` | Default provider | `openai`, `elevenlabs`, `pyttsx3`, or `auto` |
| `OPENAI_API_KEY` | OpenAI authentication | `sk-proj-...` |
| `OPENAI_TTS_VOICE` | Voice selection | `alloy`, `echo`, `fable`, `onyx`, `nova`, `shimmer` |
| `OPENAI_TTS_MODEL` | Model quality | `tts-1` (standard) or `tts-1-hd` (high quality) |
| `ELEVENLABS_API_KEY` | ElevenLabs authentication | `sk_...` |
| `ENGINEER_NAME` | Personalization | Your name |

### Provider Cost Comparison

| Provider | Cost per 1,000 chars | 10K chars/day | Monthly (300K) |
|----------|---------------------|---------------|----------------|
| OpenAI (tts-1) | $0.015 | $0.15/day | $4.50/month |
| OpenAI (tts-1-hd) | $0.030 | $0.30/day | $9.00/month |
| ElevenLabs | $0.330 | $3.30/day | $99/month |
| pyttsx3 | Free | Free | Free |

**Recommendation**: Use `openai` as default provider for 95% cost savings.

### Alternative: Using .env File

If you prefer to keep API keys separate, you can use `~/brainpods/.env`:

```bash
# Create the directory if needed
mkdir -p ~/brainpods

# Create or edit the .env file
nano ~/brainpods/.env
```

Add configuration:
```bash
# Speak TTS Configuration
TTS_ENABLED=true
TTS_PROVIDER=openai
OPENAI_API_KEY=sk-proj-YOUR-KEY-HERE
ELEVENLABS_API_KEY=sk_YOUR-KEY-HERE
ENGINEER_NAME=Your Name
OPENAI_TTS_VOICE=onyx
OPENAI_TTS_MODEL=tts-1
```

The speak command will automatically load this file as a fallback.

### Reload Configuration

After editing configuration files:

```bash
# Reload ~/.bash_aliases
source ~/.bash_aliases

# Or open a new terminal window
```

## Verification & Testing

### Check PATH and Commands

```bash
# Verify ~/bin is in PATH
echo $PATH | grep -o "$HOME/bin"

# Check if speak command is found
which speak

# Expected output: /home/username/bin/speak
```

### Check Environment Variables

```bash
# Verify TTS configuration
env | grep -E "^(TTS_|OPENAI_|ELEVENLABS_|ENGINEER_)"

# Expected output:
# TTS_ENABLED=true
# TTS_PROVIDER=openai
# OPENAI_API_KEY=sk-proj-...
# OPENAI_TTS_VOICE=onyx
# OPENAI_TTS_MODEL=tts-1
# ELEVENLABS_API_KEY=sk_...
# ENGINEER_NAME=YourName
```

### Test Installation

```bash
# Check status
speak --status

# Expected output:
# TTS Status:
#   Enabled: true
#   Provider: openai
#   Available providers: openai, elevenlabs, pyttsx3
```

### Test TTS Functionality

```bash
# Test with OpenAI (default)
speak "Hello from OpenAI TTS"

# Test with specific provider
speak --provider openai "Testing OpenAI"
speak --provider pyttsx3 "Testing offline TTS"

# Test voice selection
speak --voice alloy "Testing alloy voice"
speak --voice onyx "Testing onyx voice"

# Run built-in test
speak --test
```

### Test Additional Commands

```bash
# Test cost tracking
speak-with-tracking "This shows costs"

# Test development mode (offline only)
speak-dev "Free offline TTS"
```

## Troubleshooting

### Command Not Found

**Symptom**: `bash: speak: command not found`

**Solutions**:

1. **Verify symlinks exist**:
   ```bash
   ls -la ~/bin/speak*
   ```
   If missing, recreate symlinks (Step 3).

2. **Check PATH**:
   ```bash
   echo $PATH | grep "$HOME/bin"
   ```
   If not in PATH, add to `~/.bash_aliases` (Step 4).

3. **Reload configuration**:
   ```bash
   source ~/.bash_aliases
   ```

4. **Open new terminal**: Sometimes a fresh terminal is needed for PATH changes.

### API Key Errors

**Symptom**: "API key not found" or "401 Unauthorized"

**Solutions**:

1. **Verify API key is set**:
   ```bash
   echo $OPENAI_API_KEY
   echo $ELEVENLABS_API_KEY
   ```

2. **Check key validity**:
   - OpenAI keys start with `sk-proj-` or `sk-`
   - ElevenLabs keys start with `sk_`

3. **Reload configuration**:
   ```bash
   source ~/.bash_aliases
   ```

4. **Use offline fallback**:
   ```bash
   speak --provider pyttsx3 "Testing offline"
   ```

### No Audio Output

**Symptom**: Command runs but no sound plays

**Solutions**:

1. **Check audio device**:
   ```bash
   # Test system audio
   speaker-test -t wav -c 2
   ```

2. **Verify provider**:
   ```bash
   speak --status
   ```

3. **Test offline TTS**:
   ```bash
   speak --provider pyttsx3 "Audio test"
   ```

4. **Install audio dependencies** (Linux):
   ```bash
   sudo apt-get install espeak ffmpeg libespeak1
   ```

#### WSL-Specific Audio Issues

**Symptom**: Running in WSL2 (Windows Subsystem for Linux) with no audio

**Background**: WSL2 may have WSLGd audio issues preventing native Linux audio playback. The speak app automatically detects WSL and uses Windows audio subsystem instead.

**Automatic Solution**:
- The `openai_tts.py` provider automatically detects WSL environments
- Uses `System.Windows.Media.MediaPlayer` via PowerShell for audio playback
- No manual configuration needed - audio plays through Windows

**Verification**:
```bash
# Check if running in WSL
uname -r | grep -i microsoft

# Test speak command
speak "Testing WSL audio"

# Should hear audio through Windows without any visible windows
```

**Manual Troubleshooting**:

1. **Check WSL environment detection**:
   ```bash
   python3 -c "import platform; print('WSL:', 'microsoft' in platform.uname().release.lower())"
   ```
   Should output: `WSL: True`

2. **Verify PowerShell access**:
   ```bash
   powershell.exe -Command "Write-Host 'PowerShell works'"
   ```
   Should output: `PowerShell works`

3. **Check Windows audio**:
   - Ensure Windows volume is not muted
   - Test Windows audio with any Windows application
   - Check Windows audio device settings

4. **Test direct playback**:
   ```bash
   # Generate test audio file
   speak "test" 2>&1 | grep "Selected provider"

   # Audio should play automatically through Windows
   ```

**If audio still doesn't work in WSL**:
- Restart WSL: `wsl --shutdown` (from Windows PowerShell), then reopen terminal
- Check Windows firewall isn't blocking audio
- Verify Windows audio services are running
- Try logging out/in to Windows to reset audio subsystem

### Provider-Specific Issues

#### OpenAI Issues

```bash
# Test OpenAI directly
speak --provider openai --test

# Check model and voice settings
env | grep OPENAI_TTS

# Try different voice
OPENAI_TTS_VOICE=nova speak "Testing nova voice"
```

#### ElevenLabs Issues

```bash
# Test ElevenLabs directly
speak --provider elevenlabs --test

# List available voices
speak --list-voices

# Try default voice
speak --provider elevenlabs "Testing ElevenLabs"
```

#### pyttsx3 Issues

```bash
# Install system dependencies (Linux)
sudo apt-get install espeak ffmpeg libespeak1

# Test directly
speak --provider pyttsx3 "Offline test"

# Use development mode
speak-dev "Development test"
```

### Permission Errors

**Symptom**: "Permission denied" when creating symlinks

**Solutions**:

1. **Use full paths without sudo**:
   ```bash
   ln -sf ~/speak-app/speak ~/bin/speak
   ```

2. **Check directory permissions**:
   ```bash
   ls -ld ~/bin
   ```

3. **Ensure ownership**:
   ```bash
   # Should show your username
   ls -la ~/bin/speak
   ```

### Configuration Not Loading

**Symptom**: Environment variables not set after editing `~/.bash_aliases`

**Solutions**:

1. **Source the file**:
   ```bash
   source ~/.bash_aliases
   ```

2. **Check file syntax**:
   ```bash
   bash -n ~/.bash_aliases
   ```
   No output means syntax is correct.

3. **Verify file is loaded**:
   ```bash
   grep "bash_aliases" ~/.bashrc
   ```
   Should show: `source ~/.bash_aliases` or similar.

4. **Check for errors**:
   ```bash
   cat ~/.bash_aliases
   ```
   Look for syntax errors or typos.

## Next Steps

After successful installation:

1. **Read the Quick Start Guide**: See [README.md](README.md) for usage examples
2. **Configure Voice Preferences**: See [SETUP_OPENAI.md](SETUP_OPENAI.md) for voice options
3. **Explore Integrations**: See [docs/INTEGRATION.md](docs/INTEGRATION.md) for script integration
4. **Set Up Claude Code Hooks**: See [docs/CLAUDE_CODE_INTEGRATION.md](docs/CLAUDE_CODE_INTEGRATION.md)
5. **Review Cost Optimization**: Use `speak-dev` for free offline speech and see [docs/PROVIDERS.md](docs/PROVIDERS.md) for provider prices

## Getting Help

- **Documentation**: Check [docs/](docs/) directory for detailed guides
- **Issues**: Report problems at the GitHub repository
- **Testing**: Run `pytest` in the speak-app directory for comprehensive tests

## Uninstallation

To remove the speak installation:

```bash
# Remove symlinks
rm ~/bin/speak*

# Remove configuration from ~/.bash_aliases
nano ~/.bash_aliases
# (manually remove the "Speak App TTS Configuration" section)

# Remove repository (optional)
rm -rf ~/speak-app

# Reload shell
source ~/.bash_aliases
```
