# TAGLINE
Запускать остановленные контейнеры. Больше информации: <https://docs.docker.com/reference/cli/docker/container/start/>.
# TLDR


- Запустить контейнер Docker:

```
docker {{[start|container start]}} {{контейнер}}
```

- Запустить контейнер, подключившись к `stdout` и `stderr` и перенаправляя сигналы:

```
docker {{[start|container start]}} {{[-a|--attach]}} {{контейнер}}
```

- Запустить один или несколько контейнеров:

```
docker {{[start|container start]}} {{контейнер1 контейнер2 ...}}
```

- Показать справку:

```
docker {{[start|container start]}} --help
```