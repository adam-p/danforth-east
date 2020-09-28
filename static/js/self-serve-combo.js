/*
 * Copyright Adam Pritchard 2014
 * MIT License : https://adampritchard.mit-license.org/
 */

$(function() {
  "use strict";

  $('.mode-chooser button').click(function() {
    setMode(this.value);
    $('.mode-chooser').hide();
  });

  function setMode(mode) {
    if (mode === 'member') {
      $('#newMember').show();
      $('#newVolunteer').hide();
    }
    else { // volunteer
      $('#newMember').hide();
      $('#newVolunteer').show();
    }
  }
});
