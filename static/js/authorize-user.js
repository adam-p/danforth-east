/*
 * Copyright Adam Pritchard 2014
 * MIT License : http://adampritchard.mit-license.org/
 */

$(function() {
  "use strict";

  $('#authorizeUser form').bootstrapValidator();
  $('#authorizeUser button[type="submit"]').click(onSubmitAuthorizeUser);

  DECA.setupWaitModal($('#authorizeUser .waitModal'), onSubmitAuthorizeUser);

  function onSubmitAuthorizeUser(event) {
    if (event) {
      event.preventDefault();
    }

    var $form = $('#authorizeUser form');

    $form.data('bootstrapValidator').validate();
    if (!$form.data('bootstrapValidator').isValid()) {
      var $badElems = $('.has-error');
      $badElems.eq(0).find('input').focus();
      $('html, body').animate({
        scrollTop: $badElems.eq(0).offset().top
      });
      $badElems.addClass('bg-danger', 1000, function() {
        $(this).removeClass('bg-danger', 3000);
      });
      return false;
    }

    var data = $form.serializeObject();
    console.log(data);

    DECA.waitModalShow($('#authorizeUser .waitModal'));

    var jqxhr = $.post('', data)
        .done(function() {
          console.log('success', arguments);
          DECA.waitModalSuccess($('#authorizeUser .waitModal'));
        })
        .fail(function() {
          console.log('fail', arguments);

          // Retry on server errors.
          var retry = (jqxhr.status >= 500 && jqxhr.status < 600);

          DECA.waitModalError($('#authorizeUser .waitModal'), jqxhr.statusText,
                              jqxhr.responseText, retry);
        });
    console.log('jqxhr', jqxhr);

    return false;
  }
});
