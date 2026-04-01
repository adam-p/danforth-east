import config


def _valid_member(**overrides):
    base = {
        'First Name': 'Jane',
        'Last Name': 'Doe',
        'Email': 'jane@example.com',
        'Street Number': '123',
        'Street Name': 'Main St',
        'City': 'Toronto',
        'Postal Code': 'M4E 1A1',
    }
    base.update(overrides)
    return base


class TestValidateObjAgainstFields:
    def test_valid_member_passes(self):
        result = config.validate_member(_valid_member())
        assert result is not False

    def test_result_contains_submitted_values(self):
        result = config.validate_member(_valid_member())
        assert result['Email'] == 'jane@example.com'

    def test_missing_required_field_fails(self):
        member = _valid_member()
        del member['First Name']
        assert config.validate_member(member) is False

    def test_invalid_email_fails(self):
        assert config.validate_member(_valid_member(**{'Email': 'not-an-email'})) is False

    def test_extra_fields_are_excluded_from_result(self):
        member = _valid_member(**{'Not A Real Field': 'ignored'})
        result = config.validate_member(member)
        assert result is not False
        assert 'Not A Real Field' not in result

    def test_absent_optional_field_defaults_to_none(self):
        result = config.validate_member(_valid_member())
        assert result is not False
        assert result['Phone Number'] is None
