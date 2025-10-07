#!/bin/bash

############ [1] Batching Run ############
PROJECT_DIR="./"

############
LABEL="octotools"

THREADS=8
TASK="gpqa"
DATA_FILE="$TASK/data/data.json"
LOG_DIR="$TASK/logs/$LABEL"
OUT_DIR="$TASK/results/$LABEL"
CACHE_DIR="$TASK/cache"

LLM="gpt-4o-mini"

ENABLED_TOOLS="Generalist_Solution_Generator_Tool,Wikipedia_Knowledge_Searcher_Tool"
############

cd $PROJECT_DIR
mkdir -p $LOG_DIR

# Define the array of specific indices
indices=($(seq 100 107))

# Skip indices if the output file already exists
new_indices=()
for i in "${indices[@]}"; do
    if [ ! -f "$OUT_DIR/output_$i.json" ]; then
        new_indices+=($i)
    else
        echo "Output file already exists: $OUT_DIR/output_$i.json"
    fi
done
indices=("${new_indices[@]}")
echo "Final indices: ${indices[@]}"

# Check if indices array is empty
if [ ${#indices[@]} -eq 0 ]; then
    echo "All tasks completed."
else
    # Function to run the task for a single index
    run_task() {
        local i=$1
        echo "Running task for index $i"
        python solve.py \
        --index $i \
        --task $TASK \
        --data_file $DATA_FILE \
        --llm_engine_name $LLM \
        --root_cache_dir $CACHE_DIR \
        --output_json_dir $OUT_DIR \
        --output_types direct \
        --enabled_tools "$ENABLED_TOOLS" \
        --max_time 300 \
        2>&1 | tee $LOG_DIR/$i.log
        echo "Completed task for index $i"
        echo "------------------------"
    }

    # Export the function and variables so they can be used by parallel
    export -f run_task
    export TASK DATA_FILE LOG_DIR OUT_DIR CACHE_DIR LLM ENABLED_TOOLS

    # Run the tasks in parallel using GNU Parallel
    echo "Starting parallel execution..."
    parallel -j $THREADS run_task ::: "${indices[@]}"
    echo "All tasks completed."
fi
