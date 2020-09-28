/*
 * Copyright Adam Pritchard 2020
 * MIT License: https: //adampritchard.mit-license.org/
 */

/*
This file is used for both log in and log out.
*/

function onGapiInit() {
  if (location.pathname.endsWith('login')) {
    gapi.signin2.render('my-signin2', {
      'scope': 'profile email',
      'width': 240,
      'height': 50,
      'longtitle': true,
      'theme': 'dark',
      'onsuccess': onSignIn,
      'onfailure': onSignInFailure
    });
  } else { // logout
    gapi.load('auth2', function () {
      gapi.auth2.init();
      var auth2 = gapi.auth2.getAuthInstance();
      auth2.signOut();
    });
  }
}
// We're not guaranteed to have created this function before the GAPI script was loaded
// and the attempt was made to call it. So...
if (window.gapi) {
  onGapiInit();
}

function onSignIn(googleUser) {
  let id_token = googleUser.getAuthResponse().id_token;

  // Add a custom header to help with CSRF mitigation.
  $.ajaxSetup({
    headers: {
      'X-Requested-With': 'XMLHttpRequest',
      'Content-Type': 'application/x-www-form-urlencoded'
    }
  });

  $('#signin_failed').attr('hidden', '');

  let payload = 'idtoken=' + id_token + '&csrf_token=' + $('#csrf_token').val();
  let jqxhr = $.post('tokensignin', payload)
    .done(function () {
      console.log('success', arguments);
      console.log('Signed in as: ' + jqxhr.responseText);
      location.href = '/';
    })
    .fail(function () {
      console.log('fail', arguments);
      $('#signin_failed').removeAttr('hidden');
      $('#signin_failed_reason').text(jqxhr.responseText);
      console.log('Sign-in failed: ', jqxhr.status, jqxhr.responseText);
      // We can't proceed with this user, so sign them out from our app
      gapi.auth2.init();
      let auth2 = gapi.auth2.getAuthInstance();
      auth2.disconnect();
      auth2.signOut();
    });

  console.log('jqxhr', jqxhr);
}

function onSignInFailure(error) {
  console.log(error);
}
