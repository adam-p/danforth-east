/*
 * Copyright Adam Pritchard 2014
 * MIT License : https://adampritchard.mit-license.org/
 */

$(function() {
  "use strict";

  DECA.setupMemberFormSubmit('create',
                             '#newMember form',
                             '#newMember .waitModal',
                             '#newMember button[type="submit"]');
});
