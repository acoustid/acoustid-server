function renderFingerprintData(ctx, fp)
{
    var pixels = ctx.createImageData(32, fp.length);
    var idx = 0;
    for (var i = 0; i < fp.length; i++) {
        for (var j = 0; j < 32; j++) {
            if (fp[i] & (1 << j)) {
                pixels.data[idx + 0] = 255;
                pixels.data[idx + 1] = 255;
                pixels.data[idx + 2] = 255;
            }
            else {
                pixels.data[idx + 0] = 0;
                pixels.data[idx + 1] = 0;
                pixels.data[idx + 2] = 0;
            }
            pixels.data[idx + 3] = 255;
            idx += 4;
        }
    }
    return pixels;
}

function paintFingerprint(canvas, fp)
{
    var ctx = canvas.getContext('2d');
    var pixels = renderFingerprintData(ctx, fp);
    canvas.width = pixels.width;
    canvas.height = pixels.height;
    ctx.putImageData(pixels, 0, 0);
}

function paintFingerprintDiff(canvas, fp1, fp2, offset)
{
    var offset1 = 0, offset2 = 0;
    if (offset > 0) {
        offset1 += offset;
    }
    else {
        offset2 -= offset;
    }
    var fpDiff = [];
    fpDiff.length = Math.min(fp1.length, fp2.length) - Math.abs(offset);
    for (var i = 0; i < fpDiff.length; i++) {
        fpDiff[i] = fp1[i + offset2] ^ fp2[i + offset1];
    }

    var ctx = canvas.getContext('2d');
    var pixels1 = renderFingerprintData(ctx, fp1);
    var pixels2 = renderFingerprintData(ctx, fp2);
    var pixelsDiff = renderFingerprintData(ctx, fpDiff);

    canvas.width = pixels1.width + 2 + pixels2.width + 2 + pixelsDiff.width;
    canvas.height = Math.max(pixels1.height, pixels2.height) + Math.abs(offset);

    ctx.rect(0, 0, canvas.width, canvas.height);
    ctx.fillStyle = "#C5C5C5";
    ctx.fill();

    ctx.putImageData(pixels1, 0, offset1);
    ctx.putImageData(pixels2, pixels1.width + 2, offset2);
    ctx.putImageData(pixelsDiff, pixels1.width + 2 + pixels2.width + 2, Math.abs(offset));
}

