#!/usr/bin/bash
# Keep both panes alive, and recreate tmux if its client/server exits.
kind=${1:?Expected cava or matrix}
case "$kind" in cava|matrix) ;; *) exit 2 ;; esac
support="$HOME/.config/omalauncher/widgets"
if [[ ${2-} == pane ]]; then
    while :; do
        case ${3-} in
            shell) bash -i ;;
            animation)
                if [[ $kind == matrix ]]; then
                    bash "$support/matrix-terminal/rain.sh"
                else
                    cava
                fi
                ;;
            *) exit 2 ;;
        esac
        # Avoid a busy loop if audio or terminal initialization fails.
        sleep 2
    done
fi
socket="owl-${kind}-recovery-$$"
runner="$support/terminal-support/session.sh"
cleanup() {
    tmux -L "$socket" kill-server 2>/dev/null || :
}
trap 'exit 0' HUP INT TERM
trap cleanup EXIT
while :; do
    tmux -L "$socket" -f /dev/null \
        new-session -d -s "$kind" -n shell "exec bash '$runner' '$kind' pane shell" \; \
        new-window -t "$kind:" -n animation "exec bash '$runner' '$kind' pane animation" \; \
        set-hook -w -t "$kind:animation" window-resized "respawn-pane -k -t $kind:animation" \; \
        set-option -g status off \; \
        set-option -g focus-events on \; \
        set-hook -g client-focus-in "select-window -t $kind:shell" \; \
        set-hook -g client-focus-out "select-window -t $kind:animation" \; \
        select-window -t "$kind:animation" \; \
        attach-session -t "$kind"
    cleanup
    sleep 2
done
