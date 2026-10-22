#!/bin/bash
# Run queue for large RL campaigns (2026-10-22). Runs are registered in $REG with their full command line;
# `watch` launches queued runs up to MAX_LIVE at once and relaunches unfinished runs whose process died
# (each resumes from its last checkpoint), up to MAX_RESTARTS times. It prints one line per event.
#
#   bash scripts/campaign.sh qa   <model> <tag> "<seeds>" <arms...>   # QA arms of launch_gated_models.sh
#   bash scripts/campaign.sh poly <model> <tag> "<seeds>" <arms...>   # poly arms of launch_poly_gated.sh
#   bash scripts/campaign.sh watch                                    # long-running scheduler
#   bash scripts/campaign.sh status
# Style checkpoints come from env vars PIRATE PIGLATIN CHINESE (style-reward arms), PCOT (pirate-CoT SFT,
# arms pcot-ctrl/pcot-pen: style monitored, not rewarded) and NORMAL (unstyled on-policy SFT, normalsft-*).
cd /home/jose/feedback-spillover-exps
CAMP=${CAMP:-logs/campaign-2026-10-22}; REG=$CAMP/registry.tsv
MAX_LIVE=${MAX_LIVE:-60}; MAX_RESTARTS=${MAX_RESTARTS:-6}
mkdir -p $CAMP/restarts; touch $REG

QA_COMMON="task=qa group_size=4 batch_size=12 num_episodes=3200 learning_rate=1e-5 max_thinking_tokens=300 max_output_tokens=600 temperature=1.0 judge_model=gpt-4.1 judge_binary=true no_answer_penalty=0 explanation_judge=true explanation_judge_model=gpt-4.1 save_every=50"
POLY_COMMON="task=poly group_size=4 batch_size=12 num_episodes=3200 learning_rate=1e-5 max_thinking_tokens=800 max_output_tokens=1000 temperature=1.0 no_answer_penalty=0 explanation_judge=true explanation_judge_model=gpt-4.1 judge_model=gpt-4.1 save_every=50"

add () {  # add <name> <module> <args...>
  local name=$1 mod=$2; shift 2
  grep -q "^$name	" $REG && { echo "already registered: $name"; return; }
  printf '%s\t%s\t%s\n' "$name" "$mod" "$*" >> $REG; echo "queued $name"; }

style () {  # style <ckpt> <desc> <weight>
  [ -n "$1" ] || { echo "MISSING_CKPT"; return; }
  echo "checkpoint=$1 style_monitor=true style_desc=$2 pirate_reward_weight=$3"; }

arms () {  # arms <env> <model> <tag> <seeds> <arms...>
  local env=$1 model=$2 tag=$3 seeds=$4; shift 4
  local common pw; [ $env = qa ] && { common=$QA_COMMON; pw=-2; } || { common=$POLY_COMMON; pw=-1; tag=poly$tag; }
  common="$common model_name=$model"
  for s in $seeds; do for arm in "$@"; do
    local mod=train_grpo extra="" name=gated-$tag-$arm-s$s
    case $arm in
      ctrl|nosft-ctrl) extra="penalty_weight=0" ;;
      pen|nosft-pen)   extra="penalty_weight=$pw" ;;
      rt)  extra="penalty_weight=$pw reward_target=true" ;;
      mf)  mod=train_grpo_mind_face; extra="penalty_weight=$pw reward_target=false" ;;
      tmf) mod=train_grpo_mind_face; extra="penalty_weight=$pw reward_target=true" ;;
      pcot-ctrl) extra="penalty_weight=0 $(style "$PCOT" pirate 0)" ;;
      pcot-pen)  extra="penalty_weight=$pw $(style "$PCOT" pirate 0)" ;;
      normalsft-ctrl) [ -n "$NORMAL" ] && extra="penalty_weight=0 checkpoint=$NORMAL" || extra=MISSING_CKPT ;;
      normalsft-pen)  [ -n "$NORMAL" ] && extra="penalty_weight=$pw checkpoint=$NORMAL" || extra=MISSING_CKPT ;;
      *sr-ctrl|*sr-pen|*-rt|*-mf|*-tmf)
        local st=${arm%%sr-*}; st=${st%%-*}; local ck
        case $st in pirate) ck=$PIRATE ;; piglatin) ck=$PIGLATIN ;; chinese) ck=$CHINESE ;; esac
        case $arm in
          *sr-ctrl) extra="penalty_weight=0 $(style "$ck" $st 1)" ;;
          *sr-pen)  extra="penalty_weight=$pw $(style "$ck" $st 1)" ;;
          *-rt)  extra="penalty_weight=$pw $(style "$ck" $st 1) reward_target=true" ;;
          *-mf)  mod=train_grpo_mind_face; extra="penalty_weight=$pw $(style "$ck" $st 1) reward_target=false" ;;
          *-tmf) mod=train_grpo_mind_face; extra="penalty_weight=$pw $(style "$ck" $st 1) reward_target=true" ;;
        esac ;;
      *) echo "unknown arm $arm"; continue ;;
    esac
    [[ $extra == *MISSING_CKPT* ]] && { echo "missing checkpoint for $arm; skipped"; continue; }
    add $name $mod "$common $extra seed=$s"
  done; done; }

is_done () {  # every checkpoints.jsonl under the run dir has a final checkpoint (both models for M&F)
  local d=logs/grpo-$1 f n=0
  for f in $(find $d -name checkpoints.jsonl 2>/dev/null); do grep -q '"final"' $f || return 1; n=$((n+1)); done
  [ $n -gt 0 ]; }
is_live () { pgrep -f "log_path=logs/grpo-$1\$" >/dev/null; }

launch () {  # launch <name> <module> <args>
  set -a; source .env; set +a
  echo "=== LAUNCH $(date -u)" >> logs/grpo-$1.log
  setsid bash -c "exec uv run python -m src.spillover.$2 $3 log_path=logs/grpo-$1 >> logs/grpo-$1.log 2>&1" < /dev/null &
}

status () {
  local q=0 l=0 d=0 f=0
  while IFS=$'\t' read -r name mod args; do
    if is_done $name; then d=$((d+1)); elif is_live $name; then l=$((l+1));
    elif [ "$(cat $CAMP/restarts/$name 2>/dev/null || echo 0)" -gt $MAX_RESTARTS ]; then f=$((f+1)); else q=$((q+1)); fi
  done < $REG
  echo "$(date -u +%H:%M) done=$d live=$l waiting=$q failed=$f"; }

watch () {
  local last=""
  while true; do
    local live=$(while IFS=$'\t' read -r name mod args; do is_live $name && echo x; done < $REG | wc -l)
    while IFS=$'\t' read -r name mod args; do
      is_done $name && continue; is_live $name && continue
      local r=$(cat $CAMP/restarts/$name 2>/dev/null || echo 0)
      [ $r -gt $MAX_RESTARTS ] && continue
      [ $live -ge $MAX_LIVE ] && break
      [ -f logs/grpo-$name.log ] && { r=$((r+1)); echo $r > $CAMP/restarts/$name; [ $r -gt $MAX_RESTARTS ] && { echo "FAILED $name (restarts exhausted)"; continue; }; echo "RELAUNCH $name (restart $r)"; }
      launch "$name" "$mod" "$args"; live=$((live+1)); sleep 5
    done < $REG
    local s=$(status); [ "${s#* }" != "$last" ] && { echo "$s"; last=${s#* }; }
    sleep ${INTERVAL:-300}
  done; }

case $1 in
  qa|poly) env=$1; shift; arms $env "$@" ;;
  watch) watch ;;
  status) status ;;
  *) sed -n 2,11p $0 ;;
esac
