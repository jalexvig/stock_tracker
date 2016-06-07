$(document).ready(function(){
  $("#submit-button").click(submitOnClick);
  $("#cancel-button").click(cancelOnClick);
});

function submitOnClick() {
  console.log('Going');
  console.log($("#notify").is(":checked"));
  $.ajax({
    type: 'POST',
    url: url_settings_post,
    data: JSON.stringify({notify: $("#notify").is(":checked")}),
    contentType: "application/json",
  });
  window.location = url_index;
};

function cancelOnClick() {
  console.log('Canceling');
  window.location = url_index;
};
