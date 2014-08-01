/*
 * Copyright Adam Pritchard 2014
 * MIT License : http://adampritchard.mit-license.org/
 */

$(function() {
  "use strict";

  var g_members = null; // to by set by fillMembersList
  fillMembersList();

  DECA.setupMemberFormSubmit('renew', '#renewMemberForm', '#submitRenewMember');

  $('#membersFilter').keypress(function(event) {
    // On phones/tablets, when the user hits the "Go" button, we want the
    // keyboard to hide. Luckily, "Go" maps to carriage-return.
    if (event.which === 13) {
      $('#membersFilter').blur();
    }
  });

  function fillMembersList() {
    var jqxhr = $.getJSON('/all-members-json')
        .done(function(data, textStatus, jqxhr) {
          g_members = data.members;

          // Get rid of the "please wait" stuff.
          $('#membersListLoadSpinner').remove();
          $('#membersFilter').prop('placeholder', 'Type to find member')
                             .prop('disabled', null)
                             .focus();

          var compileMemberTemplate = _.template($('#membersListItemTemplate').html(),
                                                 null,
                                                 { 'variable': 'data',
                                                   'imports': { '$': $ } });
          var $list = $('#membersList');
          var listMembers = [];
          _.each(data.members, function(member, idx) {
            member._idx = idx;
            listMembers.push(compileMemberTemplate({member: member, fields: data.fields}));
          });

          $list.append($(listMembers.join('')));

          // Our list is filled, now set up stuff that requires it...

          $('.timeago').timeago();

          $('.member-item').click(onSelectMember);

          $('#membersFilter').fastLiveFilter(
            '#membersList',
            {
              selector: '.search-text',
              callback: function(count) {
                if (count === 0) {
                  $('#membersListNoMatch').removeClass('hidden');
                }
                else {
                  $('#membersListNoMatch').addClass('hidden');
                }
              }
            });

          // If we got a search term in our URL, apply it now
          if (window.location.hash && window.location.hash.slice(1)) {
            var searchTerm = decodeURIComponent(window.location.hash.slice(1));
            $('#membersFilter').val(searchTerm).change();
          }
        })
      .fail(function() {
          console.log('fail', arguments);
          $('#membersListLoadSpinner i').replaceWith('<i class="fa fa-warning" style="color:red"></i>');
          alert('Failed to load member list. Reload the page to try again.\n\n' +
                  jqxhr.status+': '+jqxhr.statusText+': '+jqxhr.responseText);
      });
  }

  function onSelectMember(event) {
    /*jshint validthis:true */

    event.preventDefault();

    $('.member-item').removeClass('active');
    $(this).addClass('active');

    var idx = $(this).find('[name="_idx"]').val();
    var member = g_members[idx];

    fillMemberForm(member);

    return false;
  }

  function fillMemberForm(member) {
    var $form = $('#renewMemberForm');

    $form.data('bootstrapValidator').resetForm(true);

    _.forOwn(member, function(val, name) {
      var $input = $form.find('[name="'+name+'"]');
      if ($input.length > 1) {
        // Either radio or checkbox input

        // Make sure a blank/"no" option is set if necessary.
        // Also, if we have a null value, we want "", not "null".
        val = val || '';

        if ($input.prop('type') === 'checkbox') {
          // First clear them
          $input.prop('checked', null);
          // Then set the ones that should be set
          var vals = val.split(DECA.VOLUNTEER_INTERESTS_DIVIDER);
          _.each(vals, function(val) {
            $input.filter('[value="'+val+'"]').prop('checked', 'checked');
          });

          // Trigger change handlers
          $input.change();
        }
        else { // radios
          $input.filter('[value="'+val+'"]').click().change();
        }
      }
      else {
        $input.val(val);
        $input.change();
      }
    });

    $('#reviewRenewPlaceholder').addClass('hidden');
    $('#reviewRenew').removeClass('invisible');
  }

});
