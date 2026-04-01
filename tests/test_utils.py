import utils


class TestBasicValidator:
    def test_none_optional(self):
        assert utils.basic_validator(None, False) is True

    def test_none_required(self):
        assert utils.basic_validator(None, True) is False

    def test_empty_string_optional(self):
        assert utils.basic_validator('', False) is True

    def test_empty_string_required(self):
        assert utils.basic_validator('', True) is False

    def test_string_required(self):
        assert utils.basic_validator('hello', True) is True

    def test_non_string_optional(self):
        assert utils.basic_validator(123, False) is False


class TestEmailValidator:
    def test_valid_email_required(self):
        assert utils.email_validator('user@example.com', True) is True

    def test_invalid_email(self):
        assert utils.email_validator('not-an-email', False) is False

    def test_missing_domain(self):
        assert utils.email_validator('user@', False) is False

    def test_empty_optional(self):
        assert utils.email_validator('', False) is True

    def test_empty_required(self):
        assert utils.email_validator('', True) is False

    def test_none_optional(self):
        assert utils.email_validator(None, False) is True


class TestLatlongValidator:
    def test_valid(self):
        assert utils.latlong_validator('43.6532, -79.3832', False) is True

    def test_invalid_text(self):
        assert utils.latlong_validator('invalid', False) is False

    def test_single_component(self):
        assert utils.latlong_validator('43.6532', False) is False

    def test_out_of_range(self):
        assert utils.latlong_validator('200.0, 100.0', False) is False

    def test_empty_optional(self):
        assert utils.latlong_validator('', False) is True

    def test_empty_required(self):
        assert utils.latlong_validator('', True) is False
