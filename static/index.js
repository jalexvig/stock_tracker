
$(document).ready(function(){
  $(".utc-datetime").text(updateDateTimes);
  processNotificationsOnLoadOnDelete();
  $("#create-sheet-button").click(createOnClick);
  wireRowClickHandlers(document);
});

function wireRowClickHandlers(el) {
  $(el).find(".visit-sheet").click(visitSheetOnClick);
  $(el).find(".sync-sheet").click(syncSheetOnClick);
  $(el).find(".delete-sheet").click(deleteSheetOnClick);
}

function createOnClick() {
  $.ajax({
      type: 'GET',
      url: url_create,
      dataType: 'json',
      success: function(data, status, xhr){
        var row = $(data['row_to_insert'])
        $("#sheets-table tbody").append(row)
        $(row).find('.utc-datetime').text(updateDateTimes)
        wireRowClickHandlers(row);
        processNotificationsOnCreate();
      },
      error: function(xhr, status, error){
        informUserOfSheetAccessError(xhr['status'])
      },
  })
}

function visitSheetOnClick() {
  var row = $(this).closest("tr")
  var url_visit = 'https://docs.google.com/spreadsheets/d/' + row.attr('ssheet-id')
  window.open(url_visit, '_blank')
}

function syncSheetOnClick() {
  
  var row = $(this).closest("tr")
  $.ajax({
      type: 'POST',
      url: url_sync,
      data: JSON.stringify({ssheet_id: row.attr('ssheet-id')}),
      contentType: "application/json",
      dataType: 'json',
      success: function(data, status, xhr){
        var new_time = convertToLocalDateTime(data['datetime'])
        // row.children().eq(1).text(new_time);
        row.find('.utc-datetime').text(new_time);
        if ('title' in data) {
          row.find('.sheet-title').text(data['title']);
        }
        processNotificationsOnSync();
      },
      error: function(xhr, status, error){
        informUserOfSheetAccessError(xhr['status'])
      },
  })
}

function deleteSheetOnClick() {
  var row = $(this).closest("tr")
  $.ajax({
    type: 'POST',
    url: url_delete,
    data: JSON.stringify({ssheet_id: row.attr('ssheet-id')}),
    contentType: "application/json",
    dataType: 'json',
    success: function(data, status, xhr){
      $(row).remove();
      processNotificationsOnLoadOnDelete();
    },
    error: function(xhr, status, error){
      informUserOfSheetAccessError(xhr['status'])
    },
  })
}

function updateDateTimes(index, datetime_string) {
  return convertToLocalDateTime(datetime_string)
}

function convertToLocalDateTime(old_s) {
  var format = 'MM-DD-YYYY HH:mm'
  var date = moment.utc(old_s, format).toDate()
  var new_s = moment(date).format(format)
  return new_s
}

function informUserOfSheetAccessError(statusCode) {
  
  if (statusCode == 401) {
    location.reload(true)
  } else {
    var message = "Could not perform operation.";

    if (statusCode == 403) {
      message = "You are not authorized to modify this sheet."
    } else if (statusCode == 404) {
      message = "Sheet was not found."
    } else if (statusCode == 400) {
      message = "Sheet formatted incorrectly. Make sure there are no blank rows and the first row is a header."
    }

    alert(message)
  }
}

function processNotificationsOnLoadOnDelete() {
  var rowCount = $('#sheets-table > tbody > tr').length;
  if (rowCount == 0) {
    $("#notification-add").show();
  }
}

function processNotificationsOnCreate() {
  var rowCount = $('#sheets-table > tbody > tr').length;
  if (rowCount == 1) {
    $("#notification-edit-sync").show();
  } else {
    $("#notification-edit-sync").hide();
  }
  $("#notification-add").hide();
}

function processNotificationsOnSync() {
  $("#notification-edit-sync").hide();
}
