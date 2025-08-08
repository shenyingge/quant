#!/bin/bash
# Helper script to load .env file and export variables

load_env_file() {
    local env_file="$1"
    
    if [ ! -f "$env_file" ]; then
        echo "Warning: .env file not found at $env_file"
        return 1
    fi
    
    # Read .env file and export variables
    # Skip comments and empty lines
    while IFS= read -r line || [ -n "$line" ]; do
        # Remove carriage returns and trailing whitespace
        line="${line%%$'\r'}"
        line="${line%%[[:space:]]}"
        
        # Skip comments and empty lines
        if [[ "$line" =~ ^[[:space:]]*# ]] || [[ -z "$line" ]]; then
            continue
        fi
        
        # Skip lines that don't contain =
        if [[ ! "$line" =~ = ]]; then
            continue
        fi
        
        # Export the variable
        # Remove quotes from the value if present
        var_name="${line%%=*}"
        var_value="${line#*=}"
        
        # Remove carriage returns from value
        var_value="${var_value%%$'\r'}"
        
        # Remove leading/trailing quotes
        var_value="${var_value%\"}"
        var_value="${var_value#\"}"
        var_value="${var_value%\'}"
        var_value="${var_value#\'}"
        
        # Export the variable
        export "$var_name=$var_value"
        
    done < "$env_file"
    
    return 0
}