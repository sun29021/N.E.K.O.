"""Voice: interfaces plus optional adapters. Every adapter imports its heavy
dependency lazily and raises PeripheralUnavailableError with install
instructions when it is missing, so text-only mode always works."""
