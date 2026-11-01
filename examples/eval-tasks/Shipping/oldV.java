public class oldV {
    // before: 5 plus 1 per 2 kg over 10 kg; free from a total of 100
    //         (express is not handled here yet)
    public static double snippet(int weight, int total, int express) {
        int fee = 0;
        int extra = 0;
        fee = 5;
        if (weight > 10) {
            extra = (weight - 10) / 2;
        }
        fee = fee + extra;
        if (total >= 100) {
            fee = 0;
        }
        return fee;
    }
}
