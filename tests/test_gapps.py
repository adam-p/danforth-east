import gapps
import config

_F = config.SHEETS.member.fields


def _member_dict(**overrides):
    """Minimal member dict with all fields set to empty string."""
    d = {field.name: '' for field in _F._asdict().values()}
    d.update(overrides)
    return d


class TestMemberRenewalMatcher:
    def test_matches_by_paypal_payer_id(self):
        d = _member_dict(**{_F.paypal_payer_id.name: 'ABC123'})
        assert gapps._member_renewal_matcher('', 'ABC123', d) is True

    def test_no_match_on_wrong_paypal_payer_id(self):
        d = _member_dict(**{
            _F.paypal_payer_id.name: 'ABC123',
            _F.email.name: 'member@example.com',
            _F.paypal_email.name: 'member@example.com',
        })
        assert gapps._member_renewal_matcher('other@example.com', 'WRONG', d) is False

    def test_matches_by_email(self):
        d = _member_dict(**{_F.email.name: 'user@example.com'})
        assert gapps._member_renewal_matcher('user@example.com', '', d) is True

    def test_matches_by_paypal_email(self):
        d = _member_dict(**{
            _F.email.name: 'other@example.com',
            _F.paypal_email.name: 'paypal@example.com',
        })
        assert gapps._member_renewal_matcher('paypal@example.com', '', d) is True

    def test_no_match_when_nothing_matches(self):
        d = _member_dict(**{
            _F.email.name: 'member@example.com',
            _F.paypal_email.name: 'paypal@example.com',
            _F.paypal_payer_id.name: 'some_payer_id',
        })
        assert gapps._member_renewal_matcher('other@example.com', 'other_id', d) is False

    def test_empty_email_does_not_match_empty_paypal_email(self):
        """Operator precedence bug: the paypal_email clause fires even when email is falsy.
        When email='' and the member has paypal_email='', the buggy code returns True.
        """
        d = _member_dict(**{
            _F.email.name: 'member@example.com',
            _F.paypal_email.name: '',
            _F.paypal_payer_id.name: 'some_payer_id',
        })
        # paypal_payer_id doesn't match → falls through to email clauses
        # email='' is falsy → neither email clause should fire → should be False
        assert gapps._member_renewal_matcher('', 'nonmatching', d) is False
