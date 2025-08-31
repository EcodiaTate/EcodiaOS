# systems/simula/agent/tool_specs_additions.py
# --- AMBITIOUS UPGRADE (ADDED SPECS FOR NEW TOOLS) ---

ADDITIONAL_TOOL_SPECS = [
    {
        "name": "qora_get_goal_context",
        "description": "The best tool to use first for a broad goal. Takes a natural language goal and searches the entire codebase to find the most semantically relevant files and functions, returning a collection of detailed dossiers on them. Use this to find a starting point when you don't know which files to edit.",
        "parameters": {
            "type": "object", "properties": {
                "query_text": {"type": "string", "description": "The high-level goal, e.g., 'add JWT authentication to the API.'"},
                "top_k": {"type": "integer", "description": "Number of relevant dossiers to return.", "default": 3}
            }, "required": ["query_text"]
        }, "safety": 1
    },
    {
        "name": "nova_propose_and_auction",
        "description": "An escalation tool for extremely difficult or complex problems where other tools have failed. Submits the problem to a competitive 'market' of AI agents who propose and evaluate solutions. Returns the winning solution. This is a high-cost, powerful tool for when you are stuck.",
        "parameters": {
            "type": "object", "properties": {
                "brief": {"type": "object", "description": "An 'InnovationBrief' containing the title, context, and acceptance criteria for the problem to be solved."}
            }, "required": ["brief"]
        }, "safety": 3
    },
    {
        "name": "get_context_dossier",
        "description": "Builds and retrieves a rich context dossier for a specific file or symbol, based on a stated intent. This is the best first step for understanding existing code before modifying it.", 
        "parameters": {
            "type": "object",
            "properties": {
                "target_fqname": {
                    "type": "string",
                    "description": "The fully qualified name of the target, e.g., 'systems.simula.ContextStore' or 'systems/simula/agent/orchestrator/context.py'." 
                },
                "intent": {
                    "type": "string",
                    "description": "A clear, concise description of your goal, e.g., 'add TTL support to caching' or 'fix bug in state persistence'." 
                }
            },
            "required": ["target_fqname", "intent"]
        },
        "returns": {"type": "object"}
    },
    {
        "name": "apply_refactor",
        "description": "Applies a unified diff to the workspace and optionally runs verification tests.", 
        "parameters": {
            "type": "object",
            "properties": {
                "diff": {"type": "string", "description": "The unified diff to apply."},
                "verify_paths": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of paths to run tests against after applying the diff.", 
                },
            },
            "required": ["diff"],
        }, 
        "returns": {
            "type": "object",
            "properties": {"status": {"type": "string"}, "logs": {"type": "object"}},
        },
        "safety": 2,
    },
    {
        "name": "static_check",
        "description": "Runs static analysis tools (like ruff and mypy) on specified paths.", 
         "parameters": {
            "type": "object",
            "properties": {"paths": {"type": "array", "items": {"type": "string"}}},
            "required": ["paths"],
        },
        "returns": {"type": "object"},
        "safety": 1,
    },
    {
        "name": "run_tests",
        "description": "Runs the test suite against the specified paths.", 
        "parameters": {
            "type": "object",
            "properties": {
                "paths": {"type": "array", "items": {"type": "string"}},
                "timeout_sec": {"type": "integer", "default": 900},
            }, 
             "required": ["paths"],
        },
        "returns": {"type": "object"},
        "safety": 1,
    },
    {
        "name": "list_files",
        "description": "Lists files and directories within the repository. Essential for exploring the project structure.", 
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "The repository-relative path to a directory to list.", 
                    "default": "."
                },
                "recursive": {
                    "type": "boolean",
                    "description": "Whether to list files in all subdirectories.", 
                    "default": False
                }
            },
        },
        "returns": {"type": "object"},
        "safety": 1,
    },
     {
        "name": "read_file", 
        "description": "Reads the full content of a file at a given path. Use this to understand existing code before modifying it.", 
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "The repository-relative path to the file to read.", 
                },
            },
            "required": ["path"],
        },
        "returns": {"type": "object"},
        "safety": 1,
    },
    {
        "name": "propose_intelligent_patch",
        "description": "The most powerful and safe tool for making code changes. Takes a high-level goal, generates multiple solutions, selects the best one, and runs it through an exhaustive verification and self-correction process. Use this for any non-trivial code modification.", 
        "parameters": {
            "type": "object", "properties": {
                "goal": {"type": "string", "description": "A clear, high-level description of the task, e.g., 'Add TTL support to the caching mechanism.'"},
                "objective": {"type": "object", "description": "A structured dictionary detailing targets, contracts, and acceptance criteria for the task."}
            }, "required": ["goal", "objective"] 
        }, "safety": 2
    },
    {
        "name": "commit_plan_to_memory",
        "description": "Formulates a multi-step plan and saves it to working memory. Use this to break down complex tasks and stay on track.", 
        "parameters": {
            "type": "object", "properties": {
                "thoughts": {"type": "string", "description": "Your reasoning for creating this plan."},
                "plan": {"type": "array", "items": {"type": "string"}, "description": "An ordered list of steps to accomplish the goal."}
            }, "required": ["thoughts", "plan"] 
        }, "safety": 1
    },
    {
        "name": "generate_property_test",
        "description": "Creates a new property-based test file to find edge cases and bugs in a specific function. This is more powerful than a normal test.", 
        "parameters": {
            "type": "object", "properties": {
                "file_path": {"type": "string", "description": "The repository-relative path to the Python file containing the function."},
                "function_signature": {"type": "string", "description": "The exact signature of the function to test, e.g., 'my_func(a: int, b: str) -> bool'."}
            }, "required": ["file_path", "function_signature"] 
        }, "safety": 1
    },
    {
        "name": "reindex_code_graph",
        "description": "Triggers a full scan of the repository to build or update the powerful Qora Code Graph. Use this after making significant changes or if the agent's context (dossier) seems stale.", 
        "parameters": {
            "type": "object", "properties": {
                "root": {"type": "string", "description": "The repository root to scan.", "default": "."}
            }
        }, "safety": 2
    },
     {
        "name": "run_tests_and_diagnose_failures", 
        "description": "Runs the test suite and, if any test fails, performs a deep analysis of the error output to identify the exact location and suggest a specific fix. This is more powerful than 'run_tests'.", 
        "parameters": {
            "type": "object", "properties": {
                "paths": {"type": "array", "items": {"type": "string"}, "description": "Optional list of paths to test. Defaults to all tests."}, 
                "k_expr": {"type": "string", "description": "Optional pytest '-k' expression to run a subset of tests."}
            }
        }, "safety": 1
    },
    {
        "name": "run_system_simulation",
        "description": "The ultimate verification step. Applies a change to a parallel 'digital twin' of the entire system and runs realistic end-to-end scenarios to check for unintended consequences, performance regressions, or system-level failures.", 
        "parameters": {
            "type": "object", "properties": {
                "diff": {"type": "string", "description": "The unified diff of the proposed code change to be simulated."},
                "scenarios": {"type": "array", "items": {"type": "string"}, "description": "Optional list of scenario names to run (e.g., 'smoke_test', 'high_load'). Defaults to a standard smoke test."} 
            }, "required": ["diff"]
        }, "safety": 1
    },
    {
        "name": "file_search",
        "description": "Searches for a regex pattern within file contents, like 'grep'. Crucial for finding where a function is used or where a specific string appears.", 
        "parameters": {
            "type": "object", "properties": {
                "pattern": {"type": "string", "description": "The regular expression to search for."},
                "path": {"type": "string", "description": "The repository-relative directory or file to search in.", "default": "."}
            }, "required": ["pattern"] 
        }, "safety": 1
    },
    {
        "name": "delete_file",
        "description": "Deletes a file from the repository. Use with caution.", 
        "parameters": {
            "type": "object", "properties": {
                "path": {"type": "string", "description": "The repository-relative path of the file to delete."}
            }, "required": ["path"]
        }, "safety": 3
    },
    {
         "name": "rename_file",
        "description": "Renames or moves a file or directory.", 
        "parameters": {
            "type": "object", "properties": {
                "source_path": {"type": "string", "description": "The original repository-relative path."},
                "destination_path": {"type": "string", "description": "The new repository-relative path."}
            }, "required": ["source_path", "destination_path"]
        }, "safety": 2 
    },
    {
        "name": "qora_request_critique",
        "description": "Submits a draft code diff to a panel of specialized AI critics (Security, Efficiency, Readability) for review. Use this after generating a patch to get feedback before finalizing.", 
        "parameters": {
            "type": "object",
            "properties": {
                "diff": {"type": "string", "description": "The unified diff of the proposed code change to be reviewed."}
            },
            "required": ["diff"] 
        },
        "safety": 1
    },
    {
        "name": "qora_find_similar_failures",
        "description": "Searches the system's long-term memory for past failures that are semantically similar to the current goal. Use this before generating code to learn from past mistakes.", 
        "parameters": {
            "type": "object",
            "properties": {
                "goal": {"type": "string", "description": "The current high-level goal."}
            },
            "required": ["goal"]
        }, "safety": 1 
    },
    {
        "name": "create_directory",
        "description": "Creates a new directory, including any necessary parent directories.",
        "parameters": {
            "type": "object", "properties": {
                "path": {"type": "string", "description": "The repository-relative path of the directory to create."}
            }, "required": ["path"] 
        }, "safety": 2
    },
]