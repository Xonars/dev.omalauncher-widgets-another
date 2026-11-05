# TAGLINE

Cross-platform IDE for .NET, Mono, C#, and F#

# TLDR

**Start MonoDevelop**

```monodevelop```

**Open a solution file**

```monodevelop [solution.sln]```

**Open a project file**

```monodevelop [project.csproj]```

**Open in a new window**

```monodevelop --newwindow [solution.sln]```

**Skip splash screen**

```monodevelop --nologo```

# SYNOPSIS

**monodevelop** [_options_] [_files_...]

# PARAMETERS

**--newwindow**
> Open the given file or solution in a new window instead of focusing an existing one.

**--nologo**
> Skip the splash screen during startup.

**--ipc-tcp**
> Use a TCP socket for inter-process communication (useful when Unix sockets are unavailable).

**--perf-log**
> Enable performance logging for diagnostics.

**-v**, **--version**
> Display version information.

**-h**, **--help**
> Display usage information.

# DESCRIPTION

**monodevelop** is a cross-platform integrated development environment for .NET and Mono. It supports C#, F#, Visual Basic, and a range of other languages via add-ins. Features include code completion (IntelliSense-equivalent), an integrated debugger, version control integration (Git, Subversion), refactorings, NuGet support, and a project/solution model compatible with Microsoft Visual Studio.

On macOS the same codebase is shipped as **Visual Studio for Mac**. Linux distributions usually package it as **monodevelop**.

# CAVEATS

MonoDevelop development has slowed considerably; **Visual Studio for Mac** was discontinued by Microsoft in **August 2024**, and active .NET development on Linux/macOS has largely shifted to **Visual Studio Code** with the C# extension or **JetBrains Rider**. Recent .NET SDKs may not be fully supported.

# HISTORY

MonoDevelop began as a port of **SharpDevelop** for the Mono platform around **2003**, led by the Mono team at Ximian/Novell. It became Microsoft's **Visual Studio for Mac** after the Xamarin acquisition in **2016**. Microsoft retired Visual Studio for Mac on **31 August 2024**.

# SEE ALSO

[dotnet](/man/dotnet)(1), [msbuild](/man/msbuild)(1), [code](/man/code)(1)
