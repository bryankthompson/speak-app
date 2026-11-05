# Changelog

All notable changes to the Speak TTS Command will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **Per-repo speech control**: central registry `~/.config/speak-app/repos.json` with a gate; `speak --here`, `--repos`, `--gate`, and `--alert` for warnings that always speak. Off by default, so nothing changes until the gate is switched on. Every decision is logged to `~/.cache/speak-app/speech.log`.

## [1.2.0] - 2025-10-09

### Fixed
- **WSL2 Audio Support**: Fixed audio playback in Windows Subsystem for Linux environments
  - Added automatic WSL detection using `platform.uname().release`
  - Implemented Windows MediaPlayer integration via PowerShell for WSL environments
  - Audio now plays through Windows audio subsystem without visible windows
  - Resolves WSLGd I/O errors that prevented PulseAudio connectivity
  - Maintains pygame playback for native Linux systems
  - No manual configuration required - automatic detection and fallback

### Documentation
- Added WSL-specific troubleshooting section to INSTALLATION.md
- Updated CLAUDE.md with Audio Playback Architecture details
- Enhanced AUDIO_TEST_GUIDE.md with WSL audio testing procedures
- Documented automatic WSL detection and Windows audio integration

## [1.1.1] - 2025-01-19

### Fixed
- Fixed OpenAI provider execution error ("No module named 'openai'") by executing all provider scripts directly to respect uv shebang
- Fixed OpenAI TTS deprecation warning by replacing `stream_to_file()` with `iter_bytes()`
- Fixed provider priority to default to OpenAI for cost optimization

### Changed
- Provider priority now defaults to OpenAI → ElevenLabs → pyttsx3 (was ElevenLabs → OpenAI → pyttsx3)
- All provider scripts now execute directly with their shebang for proper `uv` dependency management
- Cost optimization: Default configuration prioritizes OpenAI for 95% cost savings

### Improved
- Better error handling for missing dependencies
- Consistent execution model across all providers
- Documentation updated to reflect cost-optimized defaults

## [1.1.0] - 2025-07-18

### Added
- **Cost Optimization Features**:
  - `speak-batch`: Batch TTS processing with caching integration
  - `speak-dev`: Development mode (always uses offline pyttsx3)
  - `speak-costs`: Cost analysis and optimization recommendations
  - `speak-with-tracking`: Real-time cost display per message
  - `set_openai_default.py`: Quick setup script for OpenAI as default
  
- **Caching System**:
  - Automatic caching of frequently used phrases (70-80% hit rate)
  - Cache management with TTL and automatic cleanup
  - Integration with batch processing for maximum efficiency
  
- **Usage Tracking**:
  - Real-time cost monitoring and reporting
  - Usage statistics by provider and voice
  - Cost projections and savings recommendations

### Changed
- OpenAI promoted as primary provider (95% cost savings vs ElevenLabs)
- Enhanced documentation with cost optimization focus
- Improved test suite with 126+ tests

### Performance
- Batch processing reduces API calls by 90%
- Caching reduces costs by 70-80% for common phrases
- 99% total cost reduction achieved (from $99/month to $0.90/month)

## [1.0.0] - 2025-07-18

### Added
- Initial release of the speak command
- Multi-provider TTS support (ElevenLabs, OpenAI, pyttsx3)
- Intelligent provider selection with automatic fallback
- Command-line interface with comprehensive options
- Pipe support for text input
- Configuration via environment variables
- Non-blocking execution for script integration
- Provider status and listing commands
- Test mode for system verification
- Silent mode (`--off`) for performance-critical operations
- Session-based enable/disable functionality
- Symlink support for proper path resolution
- Comprehensive documentation and examples

### Features
- **ElevenLabs Integration**: High-quality AI voice synthesis with API key support
- **OpenAI TTS**: Alternative cloud-based TTS provider
- **pyttsx3 Fallback**: Offline TTS for environments without internet
- **Auto-Provider Selection**: Intelligent selection based on availability
- **Error Handling**: Graceful degradation when providers fail
- **Script-Friendly**: Designed for automation and CI/CD pipelines

### Technical Details
- Written in Bash with Python TTS providers
- Uses `uv` for Python dependency management
- Supports Linux, macOS, and WSL environments
- Configuration loaded from `~/brainpods/.env`
- Non-blocking execution with timeout protection

### Known Limitations
- Voice selection not yet implemented
- Speech rate and volume controls planned for future release
- Language support currently English-only
- No audio file export capability

### Migration from Inline TTS
This release extracts and enhances the TTS functionality previously embedded in get-up-to-speed commands, making it available as a standalone global utility.

## [Unreleased]

### Added
- Claude Code integration with Dynamic Hook System
- Voice-friendly formatting for technical data
- Intelligent voice queue with pacing control
- Documentation for AI coding workflow integration
- Hook system integration examples
- Automatic espeak fallback for pyttsx3 on Linux systems
- Environment variable configuration for pyttsx3 and espeak
- pyttsx3 Configuration Guide documentation

### Enhanced
- Integration guide with Claude Code section
- README with AI coding features
- API documentation with voice queue details
- pyttsx3 error handling with specific fallback mechanism
- Voice selection logic to prevent initialization errors

### Fixed
- pyttsx3 "SetVoiceByName failed" error on Linux systems
- TTS provider execution to respect script shebangs for uv support
- Improved error messages for offline TTS troubleshooting

### Planned Features
- Voice selection per provider (`--voice` option implementation)
- Speech rate control (`--rate` option implementation)
- Volume control (`--volume` option implementation)
- Multi-language support with automatic detection
- Audio file export (`--output file.mp3`)
- Message queue system for batch processing
- Web API interface for remote access
- Integration with system notifications
- Custom provider plugin system
- Configuration file support (`~/.speakrc`)

### Under Consideration
- MacOS native `say` command integration
- Windows SAPI support
- Google Cloud TTS integration
- Amazon Polly integration
- Local AI model support (Coqui TTS)
- SSML (Speech Synthesis Markup Language) support
- Pronunciation dictionary
- Voice cloning capabilities

---

For more information about upcoming features and to contribute ideas, please visit the [project repository](https://github.com/triepod-ai/speak-app).