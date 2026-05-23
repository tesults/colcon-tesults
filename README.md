# colcon-tesults

A [colcon](https://colcon.readthedocs.io/) event handler that uploads test results to [Tesults](https://www.tesults.com) after `colcon test` completes.

## Recommendation

**If you are using GoogleTest (C++) or pytest (Python) we strongly recommend using [gtest-tesults](https://github.com/tesults/gtest-tesults) or [pytest-tesults](https://pypi.org/project/pytest-tesults/) instead.** Those integrations provide per-test reporting with descriptions, steps, custom fields, and file uploads. colcon-tesults reads JUnit XML output and provides basic pass/fail results only — no enhanced reporting.

colcon-tesults is best suited for mixed workspaces where per-package setup is not practical, or as a quick zero-config starting point.

## Installation

```bash
pip install colcon-tesults
```

Or with Pixi/RoboStack:

```bash
pixi add --pypi colcon-tesults
```

## Usage

Set `TESULTS_TARGET` to your target token and run `colcon test` as usual:

```bash
TESULTS_TARGET=token colcon test
```

colcon-tesults is enabled by default once installed. If `TESULTS_TARGET` is not set, it silently does nothing.

### Config file (optional)

Keep tokens out of scripts by using a key name and pointing to a config file:

```bash
TESULTS_TARGET=my-target TESULTS_CONFIG=/path/to/tesults.cfg colcon test
```

`tesults.cfg` format:

```
# Tesults target tokens
my-target = eyJ0eXAiOiJ...
staging   = eyJ0eXAiOiK...
```

### Build information (optional)

```bash
TESULTS_BUILD_NAME=1.0.0 \
TESULTS_BUILD_RESULT=pass \
TESULTS_BUILD_DESCRIPTION="Release build" \
TESULTS_BUILD_REASON="" \
colcon test
```

## How it works

colcon-tesults hooks into the colcon event system. After each package's tests finish (`JobEnded` event), it reads the JUnit XML output from the package's build directory. When the colcon process exits, all collected results are uploaded to Tesults in a single request.

## Documentation

[https://www.tesults.com/docs/colcon](https://www.tesults.com/docs/colcon)
