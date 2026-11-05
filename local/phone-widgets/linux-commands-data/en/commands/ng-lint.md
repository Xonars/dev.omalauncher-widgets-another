# TAGLINE

runs linting on Angular project source code

# TLDR

**Lint project**

```ng lint```

**Lint specific project**

```ng lint [project-name]```

**Fix lint issues automatically**

```ng lint --fix```

**Output in specific format**

```ng lint --format json```

# SYNOPSIS

**ng** **lint** [_project_] [_options_]

# PARAMETERS

**--fix**
> Auto-fix lint issues.

**--format** _format_
> Output format (stylish, json, etc.).

**--force**
> Succeed even with lint errors.

**--silent**
> Suppress output.

**--cache**
> Reuse the lint cache to skip files unchanged since the last run.

**--max-warnings** _N_
> Fail (exit code 1) if more than _N_ warnings are reported.

# DESCRIPTION

**ng lint** runs the configured linter on the Angular workspace. Since Angular 12, the default linter is **ESLint** (via the **@angular-eslint** plugin); earlier versions used **TSLint**, which is deprecated.

The command honours the **lint** target defined in **angular.json**, so per-project overrides (custom rule sets, tsconfig variants, file globs) are picked up automatically. Running without a project name lints every project that has a **lint** target.

# CAVEATS

Requires a configured lint target in **angular.json** (created by **ng add @angular-eslint/schematics** when migrating from TSLint). **--fix** rewrites source files in place; commit or stash beforehand. **--force** still allows the build pipeline to continue but does not silence the report.

# SEE ALSO

[ng](/man/ng)(1), [eslint](/man/eslint)(1)

