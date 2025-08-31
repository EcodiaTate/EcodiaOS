from .ast_refactor import AstMutator

MUTATORS = {
    "scaffold": AstMutator().mutate,
    "imports": AstMutator().mutate,
    "typing": AstMutator().mutate,
    "error_paths": AstMutator().mutate,
}
