# TAGLINE

command-line launcher for IntelliJ IDEA

# TLDR

**Open project**

```idea [project-directory]```

**Open file**

```idea [file.java]```

**Open at line**

```idea --line [42] [file.java]```

**Compare files**

```idea diff [file1] [file2]```

**Merge files**

```idea merge [local] [remote] [base] [output]```

**Wait for IDE** (use as $EDITOR)

```idea --wait [file]```

**Format files** with project code style

```idea format -r -s [code-style.xml] [src/]```

**Run inspections headlessly**

```idea inspect [project_dir] [inspection-profile.xml] [out_dir]```

# SYNOPSIS

**idea** [_options_] [_files_]

# PARAMETERS

_FILES_
> Files or projects to open.

**--line** _NUM_
> Open the file with the cursor at the given line number.

**--column** _NUM_
> Open at a specific column (combine with **--line**).

**diff** _file1_ _file2_
> Open the diff viewer comparing two files.

**merge** _local_ _remote_ _base_ _output_
> Open the three-way merge tool.

**format** [_options_] _files_
> Apply project code-style formatting to one or more files non-interactively.

**inspect** _project_ _profile_ _output_
> Run code inspection on a project headlessly and write the report to _output_.

**installPlugins** _id_...
> Install plugins by ID from JetBrains Marketplace or a custom repository.

**--wait**
> Block until the opened file is closed (useful as **$EDITOR**).

**nosplash**
> Skip the splash screen at startup.

**dontReopenProjects**
> Show the welcome screen instead of reopening the previous projects.

**disableNonBundledPlugins**
> Launch with only bundled plugins; helpful for troubleshooting.

**--help**
> Display help information.

# DESCRIPTION

**idea** is the command-line launcher for IntelliJ IDEA. It opens files, projects, and invokes IDE features from the terminal.

The tool supports diff, merge, and project navigation. It integrates with git and other tools requiring an editor.

# CAVEATS

Requires IntelliJ IDEA installed. Path setup needed. Resource intensive.

# HISTORY

idea is the CLI launcher for **JetBrains IntelliJ IDEA**, a popular Java IDE.

# SEE ALSO

[code](/man/code)(1), [webstorm](/man/webstorm)(1), [vim](/man/vim)(1)
