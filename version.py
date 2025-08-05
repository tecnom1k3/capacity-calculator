"""Project version information."""

__all__ = ["__version__", "VERSION_TUPLE"]

# Semantic version of the project.
__version__ = "1.0.0"
# Tuple form for programmatic comparisons.
VERSION_TUPLE = tuple(map(int, __version__.split('.')))
