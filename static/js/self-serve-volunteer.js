/*
 * Copyright Adam Pritchard 2014
 * MIT License : https://adampritchard.mit-license.org/
 */

$(function() {
  "use strict";

  var inIframe = (window !== window.top);

  // If we're in an iframe, get rid of the forced container width.
  if (inIframe) {
    $('.container:first').css('width', '100%');
  }

  // If we're in an iframe, we need to do some asynchronous work before
  // submitting, so we'll handle the submit button directly, do our work, and
  // then fire off an event to start the actual data submission.
  var $fakeSubmit = $('<div class="hidden">').appendTo('body');

  DECA.setupMemberFormSubmit('self-serve',
                             '#newVolunteer form',
                             '#newVolunteer .waitModal',
                             $fakeSubmit);

  var submitClick = function(event) {
    event.preventDefault();

    if (!inIframe || !('parentIFrame' in window)) {
      // No extra work -- just submit.
      $fakeSubmit.click();
      return false;
    }

    // Because we're in an iframe, our modal wait dialog doesn't show at the
    // correct position -- i.e., it's not necessarily visible at all when it
    // shows (it will appear at the top of the iframe). We'll ask the parent
    // window where we should put the modal.

    window.parentIFrame.sendMessage(JSON.stringify({
      action: 'get-top',
      responseID: 'self-serve-volunteer'
    }));

    return false;
  };

  var messageFromParent = function(event) {
    if (!event.originalEvent || !event.originalEvent.data) {
      return;
    }

    var data;

    try {
      data = JSON.parse(event.originalEvent.data);
    }
    catch(e) {
      // Clearly not for us.
      return;
    }

    if (data.responseID !== 'self-serve-volunteer') {
      // Not for us
      return;
    }

    if (data.message === 'get-top-response') {
      var top = data.value;

      // If `top` is negative, then the top of the iframe is in full view.
      // In that case, just use 0.
      if (top < 0) {
        top = 0;
      }

      top += 'px';

      $('#newVolunteer .modal').css('top', top);

      // Now do the actual submit.
      $fakeSubmit.click();
    }
  };

  $('#newVolunteer button[type="submit"]').click(submitClick);

  $(window).on('message', messageFromParent);
});
