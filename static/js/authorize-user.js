/*
 * Copyright Adam Pritchard 2014
 * MIT License : http://adampritchard.mit-license.org/
 */

$(function() {
  "use strict";

  $('#authorizeUserForm').bootstrapValidator();
  $('#submitAuthorizeUser').click(onSubmitAuthorizeUser);

  DECA.setupWaitModal(onSubmitAuthorizeUser);

  function onSubmitAuthorizeUser(event) {
    if (event) {
      event.preventDefault();
    }

    var $form = $('#authorizeUserForm');

    $form.data('bootstrapValidator').validate();
    if (!$form.data('bootstrapValidator').isValid()) {
      var $badElems = $('.has-error');
      $badElems.eq(0).find('input').focus();
      $('html, body').animate({
        scrollTop: $badElems.eq(0).offset().top
      });
      $badElems.addClass('bg-danger', 1000, function() {
        $(this).removeClass('bg-danger', 3000)
      });
      return false;
    }

    var data = $form.serializeObject();
    console.log(data);

    DECA.waitModalShow();

    var jqxhr = $.post('', data)
        .done(function() {
          console.log('success', arguments);
          DECA.waitModalSuccess();
        })
        .fail(function() {
          console.log('fail', arguments);

          // Retry on server errors.
          var retry = (jqxhr.status >= 500 && jqxhr.status < 600);

          DECA.waitModalError(jqxhr.statusText, jqxhr.responseText, retry);
        });
    console.log('jqxhr', jqxhr);

    return false;
  }
});
