'use strict';
const form = document.querySelector('#brief-form');
const status = document.querySelector('#form-status');
form.addEventListener('submit', (event) => {
  event.preventDefault();
  if (!form.reportValidity()) return;
  status.textContent = 'Brief validated locally. Nothing was sent.';
});
