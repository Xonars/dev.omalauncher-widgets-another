# TAGLINE

bash built-in for arithmetic evaluation

# TLDR

**Arithmetic assignment**

```let "x = 5 + 3"```

**Increment variable**

```let "count++"```

**Multiple expressions**

```let "a = 1" "b = 2" "c = a + b"```

**Comparison (exit code)**

```let "5 > 3"```

**Modulo operation**

```let "result = 10 % 3"```

# SYNOPSIS

**let** _expression_...

# PARAMETERS

_EXPRESSION_
> Arithmetic expression(s).

Operators:
> +, -, *, /, %, ** (power)
> ++, -- (increment/decrement)
> ==, !=, <, >, <=, >=
> &&, ||, !

# DESCRIPTION

**let** is a Bash (and ksh) built-in that evaluates one or more arithmetic expressions. Each expression is evaluated using the same rules as `$(( ... ))`: integer math, C-style operators, and shell variable references without the leading `$`.

The exit status is **0** if the value of the **last** evaluated expression is non-zero, and **1** if it is zero. This makes `let` usable in `if`/`while` conditions but is the inverse of typical command exit semantics — a successful arithmetic result of 0 (e.g., `let "x = 0"`) reports failure.

# CAVEATS

Bash/ksh built-in; not available in POSIX `sh` or `dash`. Integer arithmetic only — use `bc` or `awk` for floating point. The `(( ... ))` arithmetic command is generally preferred in modern Bash because it does not require quoting and has cleaner exit semantics. Returns exit code 1 when the final expression evaluates to 0, which can trigger `set -e` exits unexpectedly.

# HISTORY

let is a **Bash** built-in command for arithmetic evaluation, similar to expr but more powerful.

# SEE ALSO

[bash](/man/bash)(1), [expr](/man/expr)(1), [bc](/man/bc)(1)
