public class newV {
    // threshold kept in one place; the top grade adds 1 to the grade the first test already gave
    public static double snippet(int score) {
        int pass = 59;
        int g = 0;
        if (score > pass) {
            g = 1;
        }
        if (score > pass + 30) {
            g = g + 1;
        }
        return g;
    }
}
