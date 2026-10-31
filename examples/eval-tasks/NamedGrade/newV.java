public class newV {
    // thresholds named once; the top grade adds 1 to the grade the first test gave
    public static double snippet(int score) {
        int pass = 60;
        int top = pass + 30;
        int g = 0;
        if (score >= pass) {
            g = 1;
        }
        if (score > top) {
            g = g + 1;
        }
        return g;
    }
}
