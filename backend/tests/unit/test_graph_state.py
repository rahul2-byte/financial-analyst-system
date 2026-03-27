import pytest
from app.core.graph_state import merge_dicts


class TestMergeDicts:
    """Tests that merge_dicts performs deep merge."""

    def test_simple_merge(self):
        """Basic merge works."""
        left = {"a": 1, "b": 2}
        right = {"c": 3}
        
        result = merge_dicts(left, right)
        
        assert result == {"a": 1, "b": 2, "c": 3}
    
    def test_shallow_merge_overwrites_nested(self):
        """Shallow merge would overwrite nested dicts - deep merge preserves them."""
        left = {"agent_outputs": {"step1": {"a": 1, "b": 2}}}
        right = {"agent_outputs": {"step1": {"c": 3}}}
        
        result = merge_dicts(left, right)
        
        # CRITICAL: Should deep merge, not overwrite
        expected = {"agent_outputs": {"step1": {"a": 1, "b": 2, "c": 3}}}
        assert result == expected, f"Expected {expected}, got {result}"
    
    def test_deep_merge_three_levels(self):
        """Deep merge works for 3+ levels."""
        left = {"a": {"b": {"c": 1}}}
        right = {"a": {"b": {"d": 2}}}
        
        result = merge_dicts(left, right)
        
        expected = {"a": {"b": {"c": 1, "d": 2}}}
        assert result == expected
    
    def test_right_takes_precedence_at_top_level(self):
        """Top-level keys from right override left."""
        left = {"a": 1}
        right = {"a": 2}
        
        result = merge_dicts(left, right)
        
        assert result == {"a": 2}
    
    def test_new_keys_added(self):
        """New keys from right are added."""
        left = {"a": 1}
        right = {"b": 2}
        
        result = merge_dicts(left, right)
        
        assert result == {"a": 1, "b": 2}
    
    def test_non_dict_values_not_merged(self):
        """Non-dict values are replaced, not merged."""
        left = {"a": {"b": 1}}
        right = {"a": "string"}
        
        result = merge_dicts(left, right)
        
        assert result == {"a": "string"}
