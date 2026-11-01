#!/usr/bin/env bash
# -------------------------------------------------------------------------------------------------
# infoView.sh
# orchestration of infoView (ambient information display / kiosk)
#
# usage: infoView.sh <command> [options]
#
#   setup               create .venv (with system site packages) and install pygame/feedparser
#   start               start in background, under a supervisor that restarts it on crash
#   stop                stop gracefully (SIGTERM), SIGKILL after IVW_STOP_TIMEOUT seconds
#   restart             stop + start
#   status              show supervisor / app state
#   logs [-f] [N]       show the last N (50) log lines, -f to follow
#   run                 run in foreground (no supervisor), e.g. for debugging
#   wake                turn the display on (Wayland: wlopm, X11: xset)
#   autostart on|off    add/remove "infoView.sh start" to the labwc session autostart
#   test                run the test suite (headless, no network needed)
#
# environment overrides:
#   IVW_PYTHON          python interpreter (default: .venv/bin/python, else python3)
#   IVW_CONFIG          user config file (default: infoView.toml; see infoView.example.toml)
#   IVW_STOP_TIMEOUT    seconds to wait for a graceful stop (default 10)
#   IVW_RESTART_DELAY   seconds between restarts after a crash (default 5)
#   IVW_MAX_CRASHES     give up after this many crashes ... (default 5)
#   IVW_CRASH_WINDOW    ... within this many seconds (default 60)
#   IVW_LOG_CHECK       while running, check the log size every this many seconds (default 600;
#                       rotated above IVW_LOG_MAX bytes, default 5 MB; one old copy: infoView.log.1)
#   IVW_LOG_DIR         log + pid directory (default: logs/ in the project)
#   IVW_START_WAIT      seconds "start" waits before checking the app is up (default 3)
#   DISPLAY / WAYLAND_DISPLAY are detected when not set (e.g. when called over ssh)
#
# 2026.oct  mlabru  initial release
# -------------------------------------------------------------------------------------------------

set -u

# < paths >----------------------------------------------------------------------------------------

# project root (where this script lives)
IVW_ROOT="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"

IVW_APP="${IVW_ROOT}/infoView.py"
IVW_VENV="${IVW_ROOT}/.venv"
IVW_LOG_DIR="${IVW_LOG_DIR:-${IVW_ROOT}/logs}"
IVW_LOG="${IVW_LOG_DIR}/infoView.log"
IVW_PID="${IVW_LOG_DIR}/infoView.pid"

# labwc session autostart
IVW_AUTOSTART="${HOME}/.config/labwc/autostart"
IVW_AUTOSTART_TAG="# infoView kiosk (managed by infoView.sh)"
# tag written by the script's former name (dshView.sh): "autostart off" removes it too
IVW_AUTOSTART_TAG_OLD="# dshView kiosk (managed by dshView.sh)"

# < settings >-------------------------------------------------------------------------------------

IVW_STOP_TIMEOUT="${IVW_STOP_TIMEOUT:-10}"
IVW_RESTART_DELAY="${IVW_RESTART_DELAY:-5}"
IVW_MAX_CRASHES="${IVW_MAX_CRASHES:-5}"
IVW_CRASH_WINDOW="${IVW_CRASH_WINDOW:-60}"
IVW_START_WAIT="${IVW_START_WAIT:-3}"

# rotate the log when it gets bigger than this (bytes); while running, check every (sec)
IVW_LOG_MAX="${IVW_LOG_MAX:-$((5 * 1024 * 1024))}"
IVW_LOG_CHECK="${IVW_LOG_CHECK:-600}"

# no pygame "Hello from the pygame community" banner (output / log)
export PYGAME_HIDE_SUPPORT_PROMPT=1

# < helpers >--------------------------------------------------------------------------------------

# message to stderr
msg() { echo "infoView: $*" >&2; }

# message to the log, with timestamp
log() { echo "$(date '+%Y/%m/%d %H:%M:%S') [infoView.sh] $*" >> "${IVW_LOG}"; }

# python interpreter to use
python_bin()
{
    if [ -n "${IVW_PYTHON:-}" ]; then
        echo "${IVW_PYTHON}"
    elif [ -x "${IVW_VENV}/bin/python" ]; then
        echo "${IVW_VENV}/bin/python"
    else
        echo "python3"
    fi
}

# supervisor pid, if running (empty otherwise)
supervisor_pid()
{
    local l_pid

    [ -f "${IVW_PID}" ] || return 0
    l_pid="$(cat "${IVW_PID}" 2> /dev/null)"

    # alive and really our supervisor ? (pid may have been reused)
    if [ -n "${l_pid}" ] && kill -0 "${l_pid}" 2> /dev/null && \
       tr '\0' ' ' < "/proc/${l_pid}/cmdline" 2> /dev/null | grep -q "infoView.sh _supervise"; then
        echo "${l_pid}"
    fi
}

# pid of the app (child of the supervisor), if running
app_pid()
{
    local l_spid="$(supervisor_pid)"

    [ -n "${l_spid}" ] && pgrep -P "${l_spid}" -f "infoView.py" | head -n 1
}

# find a display when not in the graphical session (e.g. ssh)
detect_display()
{
    local l_sock

    # runtime dir (wayland socket, pulse, ...)
    export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"

    # already have a display ?
    [ -n "${DISPLAY:-}" ] || [ -n "${WAYLAND_DISPLAY:-}" ] && return 0

    # pygame/SDL2 uses X11 by default: prefer an Xwayland/X11 display that answers
    # (sockets in /tmp/.X11-unix may be stale; without xset, take the first one)
    for l_sock in /tmp/.X11-unix/X*; do
        [ -S "${l_sock}" ] || continue

        if ! command -v xset > /dev/null 2>&1 || DISPLAY=":${l_sock##*/X}" timeout 3 xset q > /dev/null 2>&1; then
            export DISPLAY=":${l_sock##*/X}"
            msg "using DISPLAY=${DISPLAY}"
            return 0
        fi
    done

    # wayland only
    for l_sock in "${XDG_RUNTIME_DIR}"/wayland-[0-9]; do
        [ -S "${l_sock}" ] || continue
        export WAYLAND_DISPLAY="${l_sock##*/}" SDL_VIDEODRIVER=wayland
        msg "using WAYLAND_DISPLAY=${WAYLAND_DISPLAY}"
        return 0
    done

    msg "no display found (set DISPLAY or WAYLAND_DISPLAY)"
    return 1
}

# rotate the log if too big (one old copy: infoView.log.1)
#   rotate_log          before start: nobody has the log open, just rename it
#   rotate_log copy     while running: the app and the supervisor keep it open in append mode,
#                       so copy + truncate (they go on writing at the new end; a line written
#                       between the copy and the truncation may be lost)
rotate_log()
{
    mkdir -p "${IVW_LOG_DIR}"

    if [ -f "${IVW_LOG}" ] && [ "$(stat -c %s "${IVW_LOG}")" -gt "${IVW_LOG_MAX}" ]; then
        if [ "${1:-}" = "copy" ]; then
            cp -f "${IVW_LOG}" "${IVW_LOG}.1" && : > "${IVW_LOG}"
        else
            mv -f "${IVW_LOG}" "${IVW_LOG}.1"
        fi
    fi
}

# < commands >-------------------------------------------------------------------------------------

cmd_setup()
{
    local l_py

    # virtual environment (system site packages: reuse the distro pygame on the Raspberry Pi)
    if [ ! -x "${IVW_VENV}/bin/python" ]; then
        msg "creating ${IVW_VENV}"
        python3 -m venv --system-site-packages "${IVW_VENV}" || { msg "venv creation failed"; return 1; }
    fi

    l_py="${IVW_VENV}/bin/python"

    # pygame (needs PNG + fonts: a pip build without SDL_image/SDL_ttf is not enough)
    if ! "${l_py}" -c "import pygame, pygame.font, sys; sys.exit(not pygame.image.get_extended())" 2> /dev/null; then
        msg "installing pygame-ce (pygame missing or built without PNG/font support)"
        "${l_py}" -m pip install --quiet pygame-ce || { msg "pygame install failed"; return 1; }
    fi

    # feedparser
    if ! "${l_py}" -c "import feedparser" 2> /dev/null; then
        msg "installing feedparser"
        "${l_py}" -m pip install --quiet feedparser || { msg "feedparser install failed"; return 1; }
    fi

    "${l_py}" -c "import pygame, feedparser; print('pygame', pygame.version.ver, '| feedparser', feedparser.__version__)" >&2
    # user config file (the app works without it, with the defaults: e.g. an example city)
    if [ ! -f "${IVW_ROOT}/infoView.toml" ]; then
        msg "no infoView.toml yet: cp infoView.example.toml infoView.toml (then set your city)"
    fi

    msg "setup ok"
}

# supervisor loop (internal: started in background by "start")
cmd_supervise()
{
    local l_py="$(python_bin)"
    local l_child="" l_rc l_now l_watch=""
    local -a l_crashes=()

    # stop request: forward to the app and leave
    trap 'log "stop requested"; [ -n "${l_child}" ] && kill -TERM "${l_child}" 2> /dev/null; wait "${l_child}" 2> /dev/null; [ -n "${l_watch}" ] && kill "${l_watch}" 2> /dev/null; rm -f "${IVW_PID}"; exit 0' TERM INT HUP

    cd "${IVW_ROOT}" || exit 1

    # a kiosk runs for months: check the log size every IVW_LOG_CHECK s (the watcher leaves
    # by itself if this supervisor is gone, e.g. killed by "stop" after the timeout). The sleep
    # runs in background so the watcher's TERM trap can end it too (no orphan sleep left)
    ( trap '[ -n "${l_sleep:-}" ] && kill "${l_sleep}" 2> /dev/null; exit 0' TERM
      while true; do
          sleep "${IVW_LOG_CHECK}" &
          l_sleep=$!
          wait "${l_sleep}"
          kill -0 $$ 2> /dev/null || exit 0
          rotate_log copy
      done ) &
    l_watch=$!

    while true; do
        log "starting app (${l_py})"

        # app (in background, so the trap above can run while it's alive)
        "${l_py}" "${IVW_APP}" >> "${IVW_LOG}" 2>&1 &
        l_child=$!
        wait "${l_child}"
        l_rc=$?
        l_child=""

        # normal exit (ESC / q / window closed / SIGTERM to the app): don't restart
        if [ "${l_rc}" -eq 0 ]; then
            log "app exited normally"
            break
        fi

        # crash: keep only the crashes inside the window
        l_now="$(date +%s)"
        l_crashes=($(for t in "${l_crashes[@]}" "${l_now}"; do [ $((l_now - t)) -lt "${IVW_CRASH_WINDOW}" ] && echo "${t}"; done))

        log "app crashed (rc=${l_rc}), ${#l_crashes[@]} crash(es) in ${IVW_CRASH_WINDOW}s"

        # crashing in a loop ?
        if [ "${#l_crashes[@]}" -ge "${IVW_MAX_CRASHES}" ]; then
            log "giving up: ${IVW_MAX_CRASHES} crashes in ${IVW_CRASH_WINDOW}s"
            break
        fi

        # in background + wait: a stop request (trap) is handled at once, not after the sleep
        sleep "${IVW_RESTART_DELAY}" &
        wait $!
    done

    kill "${l_watch}" 2> /dev/null
    rm -f "${IVW_PID}"
}

cmd_start()
{
    local l_spid

    # one start at a time (e.g. the autostart and a manual start together): the lock is held
    # only while starting (closed for the supervisor, released when this script ends)
    if command -v flock > /dev/null 2>&1; then
        mkdir -p "${IVW_LOG_DIR}"
        exec 9> "${IVW_LOG_DIR}/infoView.lock"
        flock -n 9 || { msg "another start is in progress"; return 1; }
    fi

    l_spid="$(supervisor_pid)"

    # already running ?
    if [ -n "${l_spid}" ]; then
        msg "already running (supervisor pid ${l_spid})"
        return 0
    fi

    [ -f "${IVW_APP}" ] || { msg "${IVW_APP} not found"; return 1; }

    detect_display || return 1
    rotate_log

    # supervisor in its own session, detached from this terminal
    setsid nohup "${IVW_ROOT}/infoView.sh" _supervise > /dev/null 2>&1 < /dev/null 9>&- &
    echo $! > "${IVW_PID}"

    # give it a moment and check the app is up
    sleep "${IVW_START_WAIT}"

    if [ -n "$(app_pid)" ]; then
        msg "started (supervisor pid $(supervisor_pid), app pid $(app_pid)), log: ${IVW_LOG}"
    elif [ -n "$(supervisor_pid)" ]; then
        msg "supervisor running but app not up yet (restarting?), check: infoView.sh logs"
    else
        msg "failed to start, last log lines:"
        tail -n 15 "${IVW_LOG}" >&2
        return 1
    fi
}

cmd_stop()
{
    local l_spid="$(supervisor_pid)"
    local l_apid="$(app_pid)"
    local l_i

    if [ -z "${l_spid}" ]; then
        msg "not running"
        rm -f "${IVW_PID}"
        return 0
    fi

    # graceful: the supervisor forwards SIGTERM to the app (which stops its main loop)
    kill -TERM "${l_spid}" 2> /dev/null

    # wait until both supervisor and app are gone
    for ((l_i = 0; l_i < IVW_STOP_TIMEOUT * 10; l_i++)); do
        if ! kill -0 "${l_spid}" 2> /dev/null && { [ -z "${l_apid}" ] || ! kill -0 "${l_apid}" 2> /dev/null; }; then
            break
        fi
        sleep 0.1
    done

    # still alive ? force it
    if kill -0 "${l_spid}" 2> /dev/null || { [ -n "${l_apid}" ] && kill -0 "${l_apid}" 2> /dev/null; }; then
        msg "no graceful stop in ${IVW_STOP_TIMEOUT}s, killing"
        log "forced stop (SIGKILL)"
        [ -n "${l_apid}" ] && kill -KILL "${l_apid}" 2> /dev/null
        kill -KILL "${l_spid}" 2> /dev/null
    fi

    rm -f "${IVW_PID}"
    msg "stopped"
}

cmd_status()
{
    local l_spid="$(supervisor_pid)"
    local l_apid="$(app_pid)"

    if [ -z "${l_spid}" ]; then
        msg "not running"
        [ -f "${IVW_LOG}" ] && { echo "last log lines:"; tail -n 5 "${IVW_LOG}"; }
        return 3
    fi

    echo "supervisor: pid ${l_spid}"

    if [ -n "${l_apid}" ]; then
        echo "app:        pid ${l_apid}, $(ps -o etime= -p "${l_apid}" | xargs) up, $(ps -o %cpu=,rss= -p "${l_apid}" | awk '{printf "cpu %s%%, mem %d MB", $1, $2/1024}')"
    else
        echo "app:        not running (restart pending?)"
    fi

    echo "python:     $(python_bin)"
    echo "log:        ${IVW_LOG}"
}

cmd_logs()
{
    local l_follow="" l_lines=50 l_arg

    for l_arg in "$@"; do
        case "${l_arg}" in
            -f)        l_follow="-f" ;;
            [0-9]*)    l_lines="${l_arg}" ;;
            *)         msg "logs: unknown option ${l_arg}"; return 1 ;;
        esac
    done

    [ -f "${IVW_LOG}" ] || { msg "no log yet (${IVW_LOG})"; return 0; }
    tail -n "${l_lines}" ${l_follow} "${IVW_LOG}"
}

cmd_run()
{
    [ -z "$(supervisor_pid)" ] || { msg "running in background, stop it first (infoView.sh stop)"; return 1; }

    detect_display || return 1
    cd "${IVW_ROOT}" && exec "$(python_bin)" "${IVW_APP}"
}

cmd_test()
{
    # unittest from the project root; the tests set their own environment (tests/__init__.py)
    cd "${IVW_ROOT}" && "$(python_bin)" -m unittest discover -s tests -t . "$@"
}

cmd_wake()
{
    local l_wl

    detect_display || return 1

    # wayland socket of this session (WAYLAND_DISPLAY, else the first one found)
    l_wl="${WAYLAND_DISPLAY:-}"
    [ -n "${l_wl}" ] || l_wl="$(cd "${XDG_RUNTIME_DIR}" 2> /dev/null && ls -d wayland-[0-9] 2> /dev/null | head -n 1)"

    # wayland session (labwc): the compositor owns the outputs, xset (Xwayland) can't do it
    if [ -n "${l_wl}" ]; then
        if command -v wlopm > /dev/null 2>&1; then
            WAYLAND_DISPLAY="${l_wl}" wlopm --on '*' && { msg "display on (wlopm)"; return 0; }
        else
            msg "wayland session: install wlopm to turn the display on"
        fi
        return 1
    fi

    # X11 session with DPMS ?
    if command -v xset > /dev/null 2>&1 && xset q 2> /dev/null | grep -q "DPMS is"; then
        xset dpms force on && { msg "display on (xset)"; return 0; }
    fi

    msg "could not turn the display on (need wlopm or xset with DPMS)"
    return 1
}

cmd_autostart()
{
    case "${1:-}" in
        on)
            mkdir -p "$(dirname "${IVW_AUTOSTART}")"

            if grep -qF "${IVW_AUTOSTART_TAG}" "${IVW_AUTOSTART}" 2> /dev/null; then
                msg "autostart already on (${IVW_AUTOSTART})"
                return 0
            fi

            printf '\n%s\n%s start &\n' "${IVW_AUTOSTART_TAG}" "${IVW_ROOT}/infoView.sh" >> "${IVW_AUTOSTART}"
            msg "autostart on: added to ${IVW_AUTOSTART}"
            ;;
        off)
            if ! grep -qF -e "${IVW_AUTOSTART_TAG}" -e "${IVW_AUTOSTART_TAG_OLD}" "${IVW_AUTOSTART}" 2> /dev/null; then
                msg "autostart already off"
                return 0
            fi

            # remove the tag line and the line right after it (current and former name)
            sed -i -e "\|^${IVW_AUTOSTART_TAG}\$|,+1d" -e "\|^${IVW_AUTOSTART_TAG_OLD}\$|,+1d" "${IVW_AUTOSTART}"
            msg "autostart off: removed from ${IVW_AUTOSTART}"
            ;;
        *)
            msg "usage: infoView.sh autostart on|off"
            return 1
            ;;
    esac
}

usage()
{
    sed -n '/^# usage:/,/^# 2026/p' "${BASH_SOURCE[0]}" | sed -e 's/^# \{0,1\}//' -e '$d' >&2
}

# < main >-----------------------------------------------------------------------------------------

IVW_CMD="${1:-}"
shift || true

case "${IVW_CMD}" in
    setup)      cmd_setup ;;
    start)      cmd_start ;;
    stop)       cmd_stop ;;
    restart)    cmd_stop && cmd_start ;;
    status)     cmd_status ;;
    logs)       cmd_logs "$@" ;;
    run)        cmd_run ;;
    wake)       cmd_wake ;;
    autostart)  cmd_autostart "$@" ;;
    test)       cmd_test "$@" ;;
    _supervise) cmd_supervise ;;
    -h|--help|help|"") usage ;;
    *)          msg "unknown command: ${IVW_CMD}"; usage; exit 1 ;;
esac
