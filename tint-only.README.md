# Tint, from a trimmed Dawn

This branch is [Dawn](https://dawn.googlesource.com/dawn) with everything removed that isn't used
when building Tint (its WGSL compiler): about 2 300 files remain out of 85 000, and three submodules
out of 67. It exists so that a project using only Tint (taking WGSL as input and outputting SPIR-V
or MSL) can pin a specific version of the Tint source code without downloading the rest of the
content.

This is not where to get Dawn, and nothing is developed here. For the project itself see
[dawn.googlesource.com/dawn](https://dawn.googlesource.com/dawn) or its mirror,
[google/dawn](https://github.com/google/dawn).

## What is here, and where it came from

| Path | What it is |
| --- | --- |
| `src/tint`, `src/utils`, `src/cmake` | upstream's directories, whole |
| `CMakeLists.txt`, `third_party/CMakeLists.txt` | upstream's build files, unedited |
| `third_party/abseil-cpp`, `third_party/spirv-headers/src`, `third_party/spirv-tools/src` | submodules, at the commits upstream pins |
| `LICENSE`, `AUTHORS` | upstream's, and they cover everything here but this file |
| `README.md` | this file: the one thing on the branch that is not upstream's |

Every commit on this branch is one upstream commit with paths removed. Its last parent is that
upstream commit, and its message names it, so git itself says where a commit came from:

```sh
git log -1 --format=%B                                        # Upstream: <commit>, and the tag
git diff --name-status --no-renames <upstream> <this commit>  # `D` on every line but README.md
```

Nothing upstream wrote is edited. `.gitmodules` is upstream's too and still names all 67
submodules; three are left, and a recursive update takes those three and nothing else.

The tool that makes a commit of this branch and checks it, and the list of what is kept, are on the
branch [`tint-only-tools`](https://github.com/arcsine-project/dawn/tree/tint-only-tools). This
file's text is kept there as well, and each commit here records the revision it was taken from.

## Taking it as a submodule

Pin a commit of this branch and fetch at depth 1; the commit is all a build reads.

```sh
git submodule add --depth 1 https://github.com/arcsine-project/dawn external/dawn
git -C external/dawn submodule update --init --depth 1
```

## Building Tint

Dawn's own CMake configures from what is kept, as long as everything whose sources are gone is
switched off. This set builds a Tint that writes SPIR-V. It is run as written with Clang on Linux,
and on Windows through a parent project that sets the same options:

```sh
cmake -S external/dawn -B build/dawn -G Ninja -DCMAKE_BUILD_TYPE=Release \
    -DDAWN_FETCH_DEPENDENCIES=OFF \
    -DDAWN_BUILD_SAMPLES=OFF -DDAWN_BUILD_TESTS=OFF -DDAWN_BUILD_BENCHMARKS=OFF \
    -DDAWN_ENABLE_D3D11=OFF -DDAWN_ENABLE_D3D12=OFF -DDAWN_ENABLE_METAL=OFF \
    -DDAWN_ENABLE_VULKAN=OFF -DDAWN_ENABLE_OPENGLES=OFF -DDAWN_ENABLE_DESKTOP_GL=OFF \
    -DDAWN_ENABLE_NULL=OFF -DDAWN_ENABLE_INSTALL=OFF \
    -DDAWN_USE_GLFW=OFF -DDAWN_USE_X11=OFF -DDAWN_USE_WAYLAND=OFF \
    -DTINT_BUILD_TESTS=OFF -DTINT_BUILD_BENCHMARKS=OFF -DTINT_BUILD_FUZZERS=OFF \
    -DTINT_BUILD_CMD_TOOLS=ON \
    -DTINT_BUILD_WGSL_READER=ON -DTINT_BUILD_WGSL_WRITER=ON \
    -DTINT_BUILD_SPV_WRITER=ON -DTINT_BUILD_SPV_READER=OFF \
    -DTINT_BUILD_MSL_WRITER=OFF -DTINT_BUILD_HLSL_WRITER=OFF -DTINT_BUILD_GLSL_WRITER=OFF \
    -DTINT_BUILD_GLSL_VALIDATOR=OFF \
    -DTINT_BUILD_IR_BINARY=OFF -DDAWN_BUILD_PROTOBUF=OFF
cmake --build build/dawn --target tint_cmd_tint_cmd
```

`TINT_BUILD_IR_BINARY` is on by default upstream and wants protobuf, which is not here. With the MSL
writer on and both SPIR-V halves off, SPIRV-Tools is not needed either.

## When it moves

The branch moves rarely, and on purpose: when something that builds from it needs a fix upstream
has. A new commit is made from one of Dawn's
[release tags](https://github.com/google/dawn/tags) and goes on top; the branch only moves forward,
so a commit that was pinned once stays reachable.
