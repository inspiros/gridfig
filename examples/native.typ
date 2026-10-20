// Compile from the project root: typst compile --root . examples/native.typ output/pdf/native.pdf
#import "../lib.typ": gridfig, figure-page
#show: figure-page
#let pic(name) = image("images/" + name + ".png", width: 100%, height: 100%, fit: "contain")
#gridfig(
  (
    (pic("coast-input"), pic("coast-baseline"), pic("coast-ours")),
    (pic("dunes-input"), pic("dunes-baseline"), pic("dunes-ours")),
  ),
  top: ([Input], [Baseline], [*Ours*]),
  left: ([Coast], [Dunes]),
  bottom: ([$x_t$], [$hat(x)_0$], [$lambda = 0.7$]),
  cell-width: 36mm, side-width: 14mm, font-size: 10pt,
)
