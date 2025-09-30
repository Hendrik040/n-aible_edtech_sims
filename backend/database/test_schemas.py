

# ==================== Additional Comprehensive PersonalityTraits Tests ====================

class TestPersonalityTraitsExtended:
    """Extended test suite for PersonalityTraits with comprehensive edge case coverage."""
    
    def test_personality_traits_all_fields_mid_range_values(self):
        """Test all fields set to mid-range value of 5."""
        traits = PersonalityTraits(
            analytical=5, creative=5, assertive=5, collaborative=5,
            detail_oriented=5, risk_taking=5, empathetic=5, decisive=5
        )
        for field in ['analytical', 'creative', 'assertive', 'collaborative', 
                      'detail_oriented', 'risk_taking', 'empathetic', 'decisive']:
            assert getattr(traits, field) == 5
    
    def test_personality_traits_each_field_independently_at_zero(self):
        """Test each field can independently be set to 0."""
        fields = ['analytical', 'creative', 'assertive', 'collaborative', 
                  'detail_oriented', 'risk_taking', 'empathetic', 'decisive']
        for field_name in fields:
            traits = PersonalityTraits(**{field_name: 0})
            assert getattr(traits, field_name) == 0
    
    def test_personality_traits_each_field_independently_at_ten(self):
        """Test each field can independently be set to 10."""
        fields = ['analytical', 'creative', 'assertive', 'collaborative', 
                  'detail_oriented', 'risk_taking', 'empathetic', 'decisive']
        for field_name in fields:
            traits = PersonalityTraits(**{field_name: 10})
            assert getattr(traits, field_name) == 10
    
    def test_personality_traits_each_field_rejects_negative_one(self):
        """Test that -1 is rejected for each field."""
        fields = ['analytical', 'creative', 'assertive', 'collaborative', 
                  'detail_oriented', 'risk_taking', 'empathetic', 'decisive']
        for field_name in fields:
            with pytest.raises(ValidationError) as exc_info:
                PersonalityTraits(**{field_name: -1})
            errors = exc_info.value.errors()
            assert any(field_name in str(err['loc']) for err in errors)
    
    def test_personality_traits_each_field_rejects_eleven(self):
        """Test that 11 is rejected for each field."""
        fields = ['analytical', 'creative', 'assertive', 'collaborative', 
                  'detail_oriented', 'risk_taking', 'empathetic', 'decisive']
        for field_name in fields:
            with pytest.raises(ValidationError) as exc_info:
                PersonalityTraits(**{field_name: 11})
            errors = exc_info.value.errors()
            assert any(field_name in str(err['loc']) for err in errors)
    
    def test_personality_traits_float_truncation_various_values(self):
        """Test float truncation for various values."""
        traits = PersonalityTraits(
            analytical=0.9, creative=1.5, assertive=5.1, 
            collaborative=9.9, detail_oriented=10.0
        )
        assert traits.analytical == 0
        assert traits.creative == 1
        assert traits.assertive == 5
        assert traits.collaborative == 9
        assert traits.detail_oriented == 10
    
    def test_personality_traits_string_numbers_all_valid(self):
        """Test string number conversion for all valid values."""
        traits = PersonalityTraits(analytical="0", creative="5", assertive="10")
        assert traits.analytical == 0
        assert traits.creative == 5
        assert traits.assertive == 10
        assert all(isinstance(getattr(traits, f), int) or getattr(traits, f) is None 
                   for f in ['analytical', 'creative', 'assertive'])
    
    def test_personality_traits_extremely_large_positive_value(self):
        """Test rejection of extremely large positive value."""
        with pytest.raises(ValidationError):
            PersonalityTraits(analytical=1000000)
    
    def test_personality_traits_extremely_large_negative_value(self):
        """Test rejection of extremely large negative value."""
        with pytest.raises(ValidationError):
            PersonalityTraits(creative=-1000000)
    
    def test_personality_traits_mixed_valid_and_invalid_values(self):
        """Test that mixed valid/invalid values reports only invalid ones."""
        with pytest.raises(ValidationError) as exc_info:
            PersonalityTraits(analytical=5, creative=-2, assertive=10, collaborative=12)
        errors = exc_info.value.errors()
        assert len(errors) == 2
        error_fields = [str(err['loc']) for err in errors]
        assert any('creative' in field for field in error_fields)
        assert any('collaborative' in field for field in error_fields)
    
    def test_personality_traits_model_dump_with_partial_values(self):
        """Test model_dump with only some fields set."""
        traits = PersonalityTraits(analytical=7, assertive=3)
        dumped = traits.model_dump()
        assert dumped['analytical'] == 7
        assert dumped['assertive'] == 3
        assert dumped['creative'] is None
        assert dumped['collaborative'] is None
    
    def test_personality_traits_model_dump_exclude_none_option(self):
        """Test model_dump with exclude_none=True."""
        traits = PersonalityTraits(analytical=8, creative=None, assertive=2)
        dumped = traits.model_dump(exclude_none=True)
        assert 'analytical' in dumped
        assert 'assertive' in dumped
        assert 'creative' not in dumped
        assert len(dumped) == 2
    
    def test_personality_traits_json_serialization_complete(self):
        """Test JSON serialization with all fields."""
        traits = PersonalityTraits(
            analytical=1, creative=2, assertive=3, collaborative=4,
            detail_oriented=5, risk_taking=6, empathetic=7, decisive=8
        )
        json_str = traits.model_dump_json()
        assert 'analytical' in json_str
        assert 'decisive' in json_str
    
    def test_personality_traits_from_dict_partial(self):
        """Test creating from dictionary with partial data."""
        data = {'analytical': 9, 'empathetic': 4}
        traits = PersonalityTraits(**data)
        assert traits.analytical == 9
        assert traits.empathetic == 4
        assert traits.creative is None
    
    def test_personality_traits_model_copy_update_single_field(self):
        """Test model_copy with single field update."""
        original = PersonalityTraits(analytical=3, creative=7)
        updated = original.model_copy(update={'analytical': 9})
        assert updated.analytical == 9
        assert updated.creative == 7
        assert original.analytical == 3
    
    def test_personality_traits_model_copy_update_to_none(self):
        """Test model_copy can update field to None."""
        original = PersonalityTraits(analytical=5)
        updated = original.model_copy(update={'analytical': None})
        assert updated.analytical is None
        assert original.analytical == 5
    
    def test_personality_traits_boundary_one_and_nine(self):
        """Test boundary values 1 and 9."""
        traits = PersonalityTraits(analytical=1, creative=9)
        assert traits.analytical == 1
        assert traits.creative == 9


# ==================== Additional Comprehensive AccountLinkingRequest Tests ====================

class TestAccountLinkingRequestExtended:
    """Extended test suite for AccountLinkingRequest with comprehensive validation coverage."""
    
    def test_account_linking_link_minimal_valid_boundary(self):
        """Test link action with user_id=1 (minimum positive)."""
        request = AccountLinkingRequest(action="link", existing_user_id=1, state="s")
        assert request.action == "link"
        assert request.existing_user_id == 1
        assert request.state == "s"
        assert request.role is None
    
    def test_account_linking_create_minimal_valid_student(self):
        """Test create_separate with minimal data and student role."""
        request = AccountLinkingRequest(action="create_separate", state="x", role="student")
        assert request.action == "create_separate"
        assert request.role == "student"
        assert request.existing_user_id is None
    
    def test_account_linking_create_minimal_valid_professor(self):
        """Test create_separate with minimal data and professor role."""
        request = AccountLinkingRequest(action="create_separate", state="y", role="professor")
        assert request.action == "create_separate"
        assert request.role == "professor"
    
    def test_account_linking_link_with_unused_role_field(self):
        """Test link action ignores role field if provided."""
        request = AccountLinkingRequest(
            action="link", existing_user_id=50, state="test", role="student"
        )
        assert request.action == "link"
        assert request.existing_user_id == 50
        assert request.role == "student"
    
    def test_account_linking_create_with_unused_user_id_field(self):
        """Test create_separate action ignores user_id if provided."""
        request = AccountLinkingRequest(
            action="create_separate", existing_user_id=99, state="test", role="professor"
        )
        assert request.action == "create_separate"
        assert request.role == "professor"
        assert request.existing_user_id == 99
    
    def test_account_linking_state_empty_string(self):
        """Test that empty state string is allowed."""
        request = AccountLinkingRequest(action="link", existing_user_id=10, state="")
        assert request.state == ""
    
    def test_account_linking_state_very_long_string(self):
        """Test state with very long string (10000 chars)."""
        long_state = "a" * 10000
        request = AccountLinkingRequest(action="link", existing_user_id=20, state=long_state)
        assert len(request.state) == 10000
    
    def test_account_linking_state_special_characters_comprehensive(self):
        """Test state with comprehensive special characters."""
        special = "state\!@#$%^&*()_+-=[]{}|;:',.<>?/~`"
        request = AccountLinkingRequest(action="link", existing_user_id=30, state=special)
        assert request.state == special
    
    def test_account_linking_state_unicode_emojis(self):
        """Test state with unicode and emojis."""
        unicode_state = "test-🔐-状態-€-ñ"
        request = AccountLinkingRequest(action="link", existing_user_id=40, state=unicode_state)
        assert request.state == unicode_state
    
    def test_account_linking_state_whitespace_variations(self):
        """Test state with various whitespace."""
        request = AccountLinkingRequest(action="link", existing_user_id=50, state="  spaces  ")
        assert request.state == "  spaces  "
    
    def test_account_linking_state_newlines_and_tabs(self):
        """Test state with newlines and tabs."""
        state_with_whitespace = "line1\nline2\tline3"
        request = AccountLinkingRequest(
            action="link", existing_user_id=60, state=state_with_whitespace
        )
        assert "\n" in request.state
        assert "\t" in request.state
    
    def test_account_linking_user_id_large_positive(self):
        """Test with large positive user_id."""
        request = AccountLinkingRequest(action="link", existing_user_id=2147483647, state="max")
        assert request.existing_user_id == 2147483647
    
    def test_account_linking_user_id_string_coercion_valid(self):
        """Test user_id string coercion to int."""
        request = AccountLinkingRequest(action="link", existing_user_id="999", state="test")
        assert request.existing_user_id == 999
        assert isinstance(request.existing_user_id, int)
    
    def test_account_linking_user_id_float_coercion_truncation(self):
        """Test user_id float coercion truncates decimal."""
        request = AccountLinkingRequest(action="link", existing_user_id=123.9, state="test")
        assert request.existing_user_id == 123
    
    def test_account_linking_link_missing_user_id_field_error(self):
        """Test link without user_id field raises error."""
        with pytest.raises(ValidationError) as exc_info:
            AccountLinkingRequest(action="link", state="test")
        errors = exc_info.value.errors()
        assert any("existing_user_id is required" in str(err) for err in errors)
    
    def test_account_linking_link_explicit_none_user_id_error(self):
        """Test link with explicit None user_id raises error."""
        with pytest.raises(ValidationError) as exc_info:
            AccountLinkingRequest(action="link", existing_user_id=None, state="test")
        errors = exc_info.value.errors()
        assert any("existing_user_id is required" in str(err) for err in errors)
    
    def test_account_linking_link_zero_user_id_error(self):
        """Test link with zero user_id raises error."""
        with pytest.raises(ValidationError) as exc_info:
            AccountLinkingRequest(action="link", existing_user_id=0, state="test")
        errors = exc_info.value.errors()
        assert any("positive integer" in str(err) for err in errors)
    
    def test_account_linking_link_negative_user_id_various(self):
        """Test link rejects various negative user_ids."""
        for neg_id in [-1, -10, -999, -1000000]:
            with pytest.raises(ValidationError) as exc_info:
                AccountLinkingRequest(action="link", existing_user_id=neg_id, state="test")
            errors = exc_info.value.errors()
            assert any("positive integer" in str(err) for err in errors)
    
    def test_account_linking_create_missing_role_field_error(self):
        """Test create_separate without role field raises error."""
        with pytest.raises(ValidationError) as exc_info:
            AccountLinkingRequest(action="create_separate", state="test")
        errors = exc_info.value.errors()
        assert any("role is required" in str(err) for err in errors)
    
    def test_account_linking_create_explicit_none_role_error(self):
        """Test create_separate with explicit None role raises error."""
        with pytest.raises(ValidationError) as exc_info:
            AccountLinkingRequest(action="create_separate", state="test", role=None)
        errors = exc_info.value.errors()
        assert any("role is required" in str(err) for err in errors)
    
    def test_account_linking_invalid_action_values(self):
        """Test various invalid action values."""
        for invalid_action in ["Link", "LINK", "create", "CREATE_SEPARATE", "unlink", ""]:
            with pytest.raises(ValidationError) as exc_info:
                AccountLinkingRequest(action=invalid_action, state="test")
            errors = exc_info.value.errors()
            assert any('action' in str(err['loc']) for err in errors)
    
    def test_account_linking_invalid_role_values(self):
        """Test various invalid role values."""
        for invalid_role in ["Student", "STUDENT", "Professor", "admin", "teacher", ""]:
            with pytest.raises(ValidationError) as exc_info:
                AccountLinkingRequest(action="create_separate", state="test", role=invalid_role)
            errors = exc_info.value.errors()
            assert any('role' in str(err['loc']) for err in errors)
    
    def test_account_linking_missing_state_raises_error(self):
        """Test that missing state field raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            AccountLinkingRequest(action="link", existing_user_id=100)
        errors = exc_info.value.errors()
        assert any('state' in str(err['loc']) for err in errors)
    
    def test_account_linking_model_dump_link_complete(self):
        """Test model_dump for link action with all fields."""
        request = AccountLinkingRequest(action="link", existing_user_id=123, state="oauth-xyz")
        dumped = request.model_dump()
        assert dumped['action'] == "link"
        assert dumped['existing_user_id'] == 123
        assert dumped['state'] == "oauth-xyz"
        assert dumped['role'] is None
    
    def test_account_linking_model_dump_create_complete(self):
        """Test model_dump for create_separate action."""
        request = AccountLinkingRequest(action="create_separate", state="oauth-abc", role="student")
        dumped = request.model_dump()
        assert dumped['action'] == "create_separate"
        assert dumped['state'] == "oauth-abc"
        assert dumped['role'] == "student"
        assert dumped['existing_user_id'] is None
    
    def test_account_linking_model_dump_exclude_none_link(self):
        """Test model_dump with exclude_none for link action."""
        request = AccountLinkingRequest(action="link", existing_user_id=456, state="test")
        dumped = request.model_dump(exclude_none=True)
        assert 'action' in dumped
        assert 'existing_user_id' in dumped
        assert 'state' in dumped
        assert 'role' not in dumped
    
    def test_account_linking_model_dump_exclude_none_create(self):
        """Test model_dump with exclude_none for create_separate action."""
        request = AccountLinkingRequest(action="create_separate", state="test", role="professor")
        dumped = request.model_dump(exclude_none=True)
        assert 'action' in dumped
        assert 'state' in dumped
        assert 'role' in dumped
        assert 'existing_user_id' not in dumped
    
    def test_account_linking_json_serialization_link(self):
        """Test JSON serialization for link action."""
        request = AccountLinkingRequest(action="link", existing_user_id=789, state="json-test")
        json_str = request.model_dump_json()
        assert '"action"' in json_str
        assert '"link"' in json_str
        assert '789' in json_str
    
    def test_account_linking_json_serialization_create(self):
        """Test JSON serialization for create_separate action."""
        request = AccountLinkingRequest(action="create_separate", state="json-test", role="student")
        json_str = request.model_dump_json()
        assert '"create_separate"' in json_str
        assert '"student"' in json_str
    
    def test_account_linking_from_dict_link_action(self):
        """Test creating link request from dictionary."""
        data = {'action': 'link', 'existing_user_id': 555, 'state': 'dict-state'}
        request = AccountLinkingRequest(**data)
        assert request.action == "link"
        assert request.existing_user_id == 555
        assert request.state == 'dict-state'
    
    def test_account_linking_from_dict_create_action(self):
        """Test creating create_separate request from dictionary."""
        data = {'action': 'create_separate', 'state': 'dict-state', 'role': 'professor'}
        request = AccountLinkingRequest(**data)
        assert request.action == "create_separate"
        assert request.role == "professor"
    
    def test_account_linking_model_copy_link_update_state(self):
        """Test model_copy updating state for link action."""
        original = AccountLinkingRequest(action="link", existing_user_id=111, state="original")
        copied = original.model_copy(update={'state': 'updated'})
        assert copied.state == "updated"
        assert original.state == "original"
        assert copied.existing_user_id == 111
    
    def test_account_linking_model_copy_create_update_role(self):
        """Test model_copy updating role for create_separate action."""
        original = AccountLinkingRequest(action="create_separate", state="test", role="student")
        copied = original.model_copy(update={'role': 'professor'})
        assert copied.role == "professor"
        assert original.role == "student"
    
    def test_account_linking_model_copy_update_user_id(self):
        """Test model_copy updating user_id."""
        original = AccountLinkingRequest(action="link", existing_user_id=100, state="test")
        copied = original.model_copy(update={'existing_user_id': 200})
        assert copied.existing_user_id == 200
        assert original.existing_user_id == 100
