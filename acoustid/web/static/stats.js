$(document).ready(function() {

  Highcharts.theme = {
    colors: ['#4572A7', '#AA4643', '#89A54E', '#80699B', '#3D96AE', 
		  '#DB843D', '#92A8CD', '#A47D7C', '#B5CA92']
  };

  Highcharts.setOptions(Highcharts.theme);

  $('#chart1').highcharts({
		chart: {
			type: 'line'
		},
		title: { text: '' },
		xAxis: {
			type: 'datetime',
			dateTimeLabelFormats: {
				month: '%e. %b',
				year: '%b'
			}
		},
		yAxis: {
			title: { text: '' }
		},
		plotOptions: {
			line: {
				lineWidth: 2
			}
		},
		series: chart1_series
	});
  $('#chart2').highcharts({
		chart: {
			type: 'line'
		},
		title: { text: '' },
		xAxis: {
			type: 'datetime',
			dateTimeLabelFormats: {
				month: '%e. %b',
				year: '%b'
			}
		},
		yAxis: {
			title: { text: '' }
		},
		plotOptions: {
			line: {
				lineWidth: 2
			}
		},
		series: chart2_series
	});
});

