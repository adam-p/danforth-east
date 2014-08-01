/*
 * Copyright Adam Pritchard 2014
 * MIT License : http://adampritchard.mit-license.org/
 */

$(function() {
  "use strict";

  // TODO: Don't hardcode center
  var NEIGHBOURHOOD_CENTER = new google.maps.LatLng(43.6874995, -79.3153531);

  var mapOptions = {
    center: NEIGHBOURHOOD_CENTER,
    zoom: 15,
    mapTypeId: google.maps.MapTypeId.ROADMAP
  };

  var map = new google.maps.Map($('#map-canvas').get(0), mapOptions);

  // Try to keep the map height less than the window height, to maximize usability.
  $(window).resize(function() {
    $('#map-canvas').height($(window).height() * 0.75);
  }).trigger('resize');

  var heatmap, latLngArray = [], markerArray = [];

  var compileMemberInfoTemplate = _.template($('#memberInfoTemplate').html(),
                                             null,
                                             { 'variable': 'data',
                                               'imports': { '$': $ } });

  var jqxhr = $.getJSON('/all-members-json')
      .done(function(data, textStatus, jqxhr) {
        var i, member, latlong, name, markerLatLng, infowindow, marker,
          notShowing = 0;
        var mapBounds = new google.maps.LatLngBounds();

        for (i = 0; i < data.members.length; i++) {
          member = data.members[i];
          if (!member[data.fields.address_latlong.name]) {
            notShowing += 1;
            continue;
          }

          latlong = member[data.fields.address_latlong.name].split(', ');
          markerLatLng = new google.maps.LatLng(Number(latlong[0]), Number(latlong[1]));
          latLngArray.push(markerLatLng);
          mapBounds.extend(markerLatLng);

          marker = new google.maps.Marker({
              position: markerLatLng
          });

          markerArray.push(marker);

          marker.DECA_infowindow = new google.maps.InfoWindow({
            content: compileMemberInfoTemplate({member: member,
                                                fields: data.fields})
          });

          google.maps.event.addListener(marker, 'click', onMarkerClick);
        }

        $('#membersNotShowing').text(String(notShowing));

        map.fitBounds(mapBounds);

        heatmap = new google.maps.visualization.HeatmapLayer({
          data: latLngArray
        });

        // Show the initial map state.
        changeGradient();
        //changeRadius();
        //changeOpacity();
        showHeatmap();

        // Hide the wait spinner
        $('#loadSpinner').addClass('hidden');
      })
    .fail(function() {
        console.log('fail', arguments);
        alert('Failed to load member list. Reload the page to try again.\n\n' +
                jqxhr.status+': '+jqxhr.statusText+': '+jqxhr.responseText);
    });


  function toggleHeatmap() {
    if (!heatmap.getMap()) {
      showHeatmap();
    }
    else {
      hideHeatmap();
    }
  }
  $('#toggleHeatmap').click(toggleHeatmap);

  function showHeatmap() {
    setAllMarkersToMap(null);
    heatmap.setMap(map);
    $('.heatmap-btn').removeClass('disabled');
  }

  function hideHeatmap() {
    setAllMarkersToMap(map);
    heatmap.setMap(null);
    $('.heatmap-btn').addClass('disabled');
  }

  function setAllMarkersToMap(map) {
    for (var i = 0; i < markerArray.length; i++) {
      markerArray[i].setMap(map);
    }
  }

  function changeGradient() {
    var gradient = [
      'rgba(0, 255, 255, 0)',
      'rgba(0, 255, 255, 1)',
      'rgba(0, 191, 255, 1)',
      'rgba(0, 127, 255, 1)',
      'rgba(0, 63, 255, 1)',
      'rgba(0, 0, 255, 1)',
      'rgba(0, 0, 223, 1)',
      'rgba(0, 0, 191, 1)',
      'rgba(0, 0, 159, 1)',
      'rgba(0, 0, 127, 1)',
      'rgba(63, 0, 91, 1)',
      'rgba(127, 0, 63, 1)',
      'rgba(191, 0, 31, 1)',
      'rgba(255, 0, 0, 1)'
    ];
    heatmap.set('gradient', heatmap.get('gradient') ? null : gradient);
  }
  $('#changeGradient').click(changeGradient);

  function changeRadius() {
    heatmap.set('radius', heatmap.get('radius') ? null : 20);
  }
  $('#changeRadius').click(changeRadius);

  function changeOpacity() {
    heatmap.set('opacity', heatmap.get('opacity') ? null : 0.2);
  }
  $('#changeOpacity').click(changeOpacity);

  function onMarkerClick() {
    /*jshint validthis:true */
    for (var i = 0; i < markerArray.length; i++) {
      markerArray[i].DECA_infowindow.close();
    }

    this.DECA_infowindow.open(map, this);
  }

});
